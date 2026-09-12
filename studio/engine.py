import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, sosfiltfilt
from .rubberband import Option
from .analysis import SR, run_audio
from .storage import TRACKS, EXPORTS, read_track, save_json
from .upstream import semitones_between_keys

class Cancelled(Exception):
    pass

def check_cancel(event):
    if event.is_set():
        raise Cancelled('Abgebrochen')

def separate(track, progress, cancel):
    folder = TRACKS / track['id']
    target = folder / 'stems'
    if all((target / f'{stem}.wav').exists() for stem in ('drums', 'bass', 'other', 'vocals')):
        return target
    import torch
    device = os.environ.get('MASHUP_DEVICE', 'cpu')
    target.mkdir(exist_ok=True)
    for attempt in range(2):
        check_cancel(cancel)
        progress(0, f'Stimmen und Instrumente trennen: {track["name"]} ({device.upper()})')
        command = [sys.executable, '-m', 'demucs', '-n', 'htdemucs', '-d', device, '--shifts', '1', '--overlap', '0.25',
                   '--float32', '-j', '1', '-o', str(folder / 'separation'), str(folder / 'audio.wav')]
        env = {**os.environ, 'PYTORCH_ENABLE_MPS_FALLBACK': '1', 'OMP_NUM_THREADS': '6', 'MKL_NUM_THREADS': '6'}
        logpath = folder / 'separation.log'
        with logpath.open('w') as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
            while process.poll() is None:
                if cancel.wait(1):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise Cancelled('Abgebrochen')
        if process.returncode == 0:
            for stem in ('drums', 'bass', 'other', 'vocals'):
                (folder / 'separation/htdemucs/audio' / f'{stem}.wav').replace(target / f'{stem}.wav')
            track['separated'] = True
            save_json(folder / 'track.json', track)
            from .analysis import profile_stems
            profile_stems(track)
            return target
        if device == 'mps':
            device = 'cpu'
        else:
            raise RuntimeError('Demucs konnte den Track nicht trennen. ' + logpath.read_text()[-1800:])
    raise RuntimeError('Stimmtrennung fehlgeschlagen.')

def stretch(audio, ratio=1., semitones=0., vocal=False, keyframes=None, percussive=False):
    """Offline Rubber Band R3, one pass for time and pitch, stereo phase linked."""
    if abs(ratio-1) < .00001 and abs(semitones) < .00001 and not keyframes:
        return audio.copy()
    from .rubberband import offline
    options = int(Option.PROCESS_OFFLINE) | int(Option.ENGINE_FASTER if percussive else Option.ENGINE_FINER) | int(Option.CHANNELS_TOGETHER) | int(Option.THREADING_NEVER)
    if abs(semitones) > .00001:
        options |= int(Option.PITCH_HIGH_QUALITY)
    if vocal:
        options |= int(Option.FORMANT_PRESERVED)
    return offline(audio, SR, options, ratio, 2 ** (semitones/12), keyframes)

def fit(audio, length):
    return np.pad(audio[:length], ((0, max(0, length-len(audio))), (0, 0)))

def snap_start(start, track, bpm):
    beat = 60/bpm
    return max(0., track['downbeat'] + round((start-track['downbeat']) / beat)*beat)

def local_timing(track, start, bpm, manual=False):
    if not manual and track.get('local_grids'):
        grid = min(track['local_grids'],key=lambda g:abs((g['at']+12)-start))
        return {**track,'downbeat':grid['downbeat']}, grid['bpm']
    return track,bpm

def clip_timing(track, start, bars, bpm, manual=False):
    """Use observed bar boundaries; retain manual BPM as an explicit override."""
    path = TRACKS / track['id'] / 'beat-grid.json'
    if not manual and path.exists():
        grid = json.loads(path.read_text())
        downbeats = np.array(grid['downbeats'])
        index = int(np.argmin(abs(downbeats-start)))
        if index+bars >= len(downbeats):
            raise ValueError(f'Nicht genug vollständige Takte ab {start:.1f} s in {track["name"]}.')
        anchors = downbeats[index:index+bars+1]
        return float(anchors[0]), float(anchors[-1]), anchors-anchors[0], 'beat-this'
    local, bpm = local_timing(track, start, bpm, manual)
    snapped = snap_start(start, local, bpm)
    return snapped, snapped+bars*240/bpm, None, 'manual' if manual else 'estimated'

def read_component(folder, stem, start, frames):
    """Recombine related stems BEFORE time stretching to retain cancellation/phase."""
    names = {'harmony': ('bass', 'other'), 'instrumental': ('drums', 'bass', 'other')}.get(stem, (stem,))
    if stem == 'instrumental' and (folder/'instrumental.wav').exists():
        names = ('instrumental',)
    result = None
    for name in names:
        with sf.SoundFile(folder/f'{name}.wav') as source:
            if source.samplerate != SR or source.channels != 2:
                raise ValueError('Stems müssen 44.1 kHz Stereo sein.')
            source.seek(min(start, len(source)))
            audio = source.read(frames, dtype='float32', always_2d=True)
        if result is None:
            result = audio
        elif audio.shape != result.shape:
            raise ValueError('Die Instrumentalspuren haben unterschiedliche Längen.')
        else:
            result += audio
    return result


def timing_map(anchors, ratio, context_frames, output_context, target_bpm):
    if anchors is None:
        return None
    # Beat This! timestamps are quantized. Do not bend a steady performance
    # merely to follow <=12 ms of detector jitter in an otherwise straight grid.
    ideal = np.arange(len(anchors))*240/target_bpm
    if np.max(np.abs(np.asarray(anchors)*ratio-ideal)) <= .012:
        return None
    return {context_frames+round(float(at)*SR): output_context+round(float(to)*SR)
            for at,to in zip(anchors, ideal)}


def source_clip(track, stem, start, bars, bpm, target_bpm, shift, cancel, manual=False, tail_seconds=0., quality='auto', head_seconds=0., intro_bars=0):
    check_cancel(cancel)
    start, end, anchors, _ = clip_timing(track, start, bars, bpm, manual)
    seconds = end-start
    ratio = (bars*240/target_bpm)/seconds
    input_tail = tail_seconds/ratio
    from .separation import stems_folder
    source_start = round(start*SR)
    context = min(source_start, round((.12+head_seconds/ratio)*SR))
    stem_folder = stems_folder(track, quality)
    audio = read_component(stem_folder, stem, source_start-context,
                           context+round((seconds+input_tail)*SR))
    if len(audio)-context < SR/2:
        raise ValueError(f'Der Einstieg für {track["name"]} liegt hinter dem Songende.')
    if len(audio)-context < round(seconds*SR)-SR*.1:
        raise ValueError(f'Der Abschnitt ab {start:.1f} s in {track["name"]} ist zu lang. Einstieg oder Taktzahl ändern.')
    audio = fit(audio, context+round((seconds+input_tail)*SR))
    if intro_bars and stem != 'vocals':
        from .intro import rhythm_gain
        intro_seconds = float(anchors[intro_bars]) if anchors is not None else seconds*intro_bars/bars
        shaped_frames = min(len(audio), context+round(intro_seconds*SR))
        phase = (np.arange(shaped_frames, dtype=np.float32)-context)/max(1., intro_seconds*SR)
        # Shape the original stems, then stretch the complete signal ONCE.
        # All gains reach unity before the first vocal; its backing is intact.
        for component in (('drums', 'bass') if stem == 'instrumental' else ('bass',) if stem == 'harmony' else (stem,)):
            gain = rhythm_gain(phase, component)
            if component == stem:
                audio[:shaped_frames] *= gain[:, None]
            else:
                original = fit(read_component(stem_folder, component, source_start-context, shaped_frames), shaped_frames)
                audio[:shaped_frames] -= original*(1-gain)[:, None]
    output_context = round(context*ratio)
    mapping = timing_map(anchors, ratio, context, output_context, target_bpm)
    result = stretch(audio, ratio, shift if stem != 'drums' else 0, vocal=stem=='vocals',
                     keyframes=mapping, percussive=stem=='drums')
    head = round(head_seconds*SR)
    begin = output_context-head
    if begin < 0:
        result = np.pad(result, ((-begin, 0), (0, 0)))
        begin = 0
    return fit(result[begin:], head+round(bars*240/target_bpm*SR)+round(tail_seconds*SR))

def offset_audio(audio, beats, bpm):
    shift = round(beats*60/bpm*SR)
    if shift >= 0:
        return np.pad(audio, ((shift, 0), (0, 0)))[:len(audio)]
    return fit(audio[-shift:], len(audio))

def shape_section(vocal, bed, effect, bpm):
    n = len(bed)
    if effect == 'intro':
        low = sosfiltfilt(butter(2, 1500, fs=SR, output='sos'), bed, axis=0).astype(np.float32)
        ramp = np.linspace(0, 1, n, dtype=np.float32)[:, None]
        ramp = ramp*ramp*(3-2*ramp)
        bed = (low*(1-ramp)+bed*ramp) * (.7+.3*ramp)
    elif effect == 'build':
        high = sosfilt(butter(2, 750, btype='highpass', fs=SR, output='sos'), bed, axis=0).astype(np.float32)
        ramp = np.linspace(0, 1, n, dtype=np.float32)[:, None]**1.5
        bed = (bed*(1-ramp)+high*ramp) * (1-.22*ramp)
        gap = min(round(.5*60/bpm*SR), n)
        bed[-gap:] *= np.linspace(1, 0, gap)[:, None]**2
    elif effect == 'outro':
        fade = min(round(8*60/bpm*SR), n)
        bed[-fade:] *= np.linspace(1, 0, fade)[:, None]
        vocal[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return vocal, bed

def active_rms(audio):
    """Measure voiced blocks, so long pauses do not turn the next phrase up."""
    block = SR//20
    n = len(audio)//block
    if not n:
        return 0.
    levels = np.sqrt(np.mean(audio[:n*block].reshape(n, block, 2)**2, axis=(1, 2)))
    active = levels[levels > max(.008, float(np.quantile(levels, .9))*.22)]
    return float(np.sqrt(np.mean(active**2))) if len(active) else 0.


def duck_envelope(vocal):
    """Stereo-linked level with a short attack and a musical 180 ms release."""
    block = max(1, round(.005*SR))
    power = np.mean(vocal.astype(np.float64)**2, axis=1)
    padded = np.pad(power, (0, (-len(power)) % block))
    levels = np.sqrt(padded.reshape(-1, block).mean(axis=1))
    attack, release = np.exp(-.005/.015), np.exp(-.005/.180)
    env = np.empty(len(levels))
    previous = 0.
    for i, level in enumerate(levels):
        coefficient = attack if level > previous else release
        previous = coefficient*previous+(1-coefficient)*level
        env[i] = previous
    return np.interp(np.arange(len(vocal)), np.r_[0., np.arange(len(env))*block+block/2],
                     np.r_[0., env]).astype(np.float32)


def mix_space(vocal, bed, vocal_gain=None):
    # Run once across the joined song, so EQ and sidechain state survive edits.
    vocal = sosfilt(butter(2, 85, btype='highpass', fs=SR, output='sos'), vocal, axis=0).astype(np.float32)
    if vocal_gain is not None:
        vocal *= vocal_gain
    else:
        level = active_rms(vocal)
        if level > .008:
            vocal *= np.clip(.078/level, .5, 1.8)
    envelope = duck_envelope(vocal)
    # Zero-phase offline band extraction avoids subtracting a phase-rotated
    # midrange from the original. The remaining low/high bands stay in place.
    mid = sosfiltfilt(butter(2, [280, 4200], btype='bandpass', fs=SR, output='sos'), bed, axis=0).astype(np.float32)
    bed = bed-mid*(.23*np.clip(envelope/.10, 0, 1))[:, None]
    return vocal, bed

def join_parts(vocal_parts, bed_parts, tails, sections, continuations=None, bed_continuations=None,
               heads=None, vocal_edits=None, handle_limit=1.6):
    vocals, bed = np.concatenate(vocal_parts), np.concatenate(bed_parts)
    boundary = 0
    for i in range(1, len(sections)):
        boundary += len(vocal_parts[i-1])
        vt, bt = tails[i-1]
        # A short continuation from the actual source bridges edits, with no repeated syllable/echo.
        n = min(len(bt), round((.008 if sections[i].effect=='drop' else .025)*SR))
        if n and sections[i-1].effect not in ('build', 'outro') and not (bed_continuations and bed_continuations[i]):
            ramp = np.linspace(0, 1, n)[:, None]
            bed[boundary:boundary+n] = bt[:n]*(1-ramp)+bed[boundary:boundary+n]*ramp
        n = min(len(vt), round(.18*SR), len(vocals)-boundary)
        if heads is None and n and not (continuations and continuations[i]):
            incoming = vocals[boundary:boundary+n]
            # Preserve a natural release only when the incoming singer leaves space.
            if active_rms(incoming) < .018:
                incoming += vt[:n]*np.linspace(1, 0, n)[:, None]
            else:
                short = min(n, round(.008*SR))
                ramp = np.linspace(0, 1, short)[:, None]
                incoming[:short] = vt[:short]*(1-ramp)+incoming[:short]*ramp
    if heads is not None:
        from .phrases import restore_vocal_edges
        edits = restore_vocal_edges(vocals, vocal_parts, heads, [t[0] for t in tails],
            continuations or [False]*len(sections), sections, SR, max(active_rms(vocals), .008), handle_limit)
        if vocal_edits is not None:
            vocal_edits.extend(edits)
    for signal in (vocals, bed):
        n = min(round(.012*SR), len(signal)//2)
        signal[:n] *= np.linspace(0, 1, n)[:, None]
        signal[-n:] *= np.linspace(1, 0, n)[:, None]
    return vocals, bed


def vocal_runs(sections, timing):
    """Keep consecutive vocal sections in one stretch pass, even when the bed changes."""
    runs = {}
    i = 0
    while i < len(sections):
        first = sections[i]
        if first.vocal == 'none':
            i += 1
            continue
        end_index = i+1
        _, end = timing(first)
        while end_index < len(sections):
            following = sections[end_index]
            if following.vocal != first.vocal or first.vocal_offset or following.vocal_offset:
                break
            begin, following_end = timing(following)
            if abs(begin-end) > .02:
                break
            end, end_index = following_end, end_index+1
        total = sum(s.bars for s in sections[i:end_index])
        preceding = 0
        for j in range(i, end_index):
            runs[j] = (i, total, preceding)
            preceding += sections[j].bars
        i = end_index
    return runs


def backing_components(section):
    return (('B', 'drums'), ('A', 'harmony')) if section.instrumental == 'hybrid' else ((section.instrumental, 'instrumental'),)


def backing_runs(sections, timing):
    """Process a continuing backing component once across arrangement sections."""
    runs = {}
    for i, section in enumerate(sections):
        for source, stem in backing_components(section):
            if (i, source, stem) in runs:
                continue
            _, end = timing(section, source)
            j = i+1
            while j < len(sections) and (source, stem) in backing_components(sections[j]):
                begin, following_end = timing(sections[j], source)
                if abs(begin-end) > .02:
                    break
                end, j = following_end, j+1
            count = sum(s.bars for s in sections[i:j])
            preceding = 0
            for k in range(i, j):
                runs[k, source, stem] = (i, count, preceding)
                preceding += sections[k].bars
    return runs

def render(request, job_id, progress, cancel):
    a, b = read_track(request.track_a), read_track(request.track_b)
    tracks = {'A': a, 'B': b}
    bpms = {'A': request.bpm_a or a['bpm'], 'B': request.bpm_b or b['bpm']}
    target = request.target_bpm or round(np.sqrt(bpms['A']*bpms['B']), 1)
    for source, bpm in bpms.items():
        if not .5 <= target/bpm <= 2:
            raise ValueError(f'Tempo von Track {source} und Ziel liegen zu weit auseinander. BPM-Prüfung nötig.')
    pitch = request.pitch_b if request.pitch_b is not None else (semitones_between_keys(b['key'], a['key']) if request.key_match else 0)
    from .separation import selected_backend, stems_folder
    backends = {name: selected_backend(track, request.separation_quality) for name,track in tracks.items()}
    for i, (name, track) in enumerate(tracks.items()):
        if backends[name] == 'standard':
            separate(track, lambda _, msg: progress(5+i*20, msg), cancel)
    folder = EXPORTS / job_id
    folder.mkdir(exist_ok=True)
    sections = request.sections
    if request.preview:
        from .intro import preview_sections
        sections = preview_sections(sections)
    vocal_parts, bed_parts, tails, heads, report = [], [], [], [], []
    from .phrases import handle_duration
    handle_seconds = handle_duration(target) if request.protect_vocal_phrases else .18
    # Read beyond the edit limit to verify the FULL bounding pause; a pause
    # near the end of a handle must not be mistaken for a short consonant gap.
    context_seconds = handle_seconds+.25 if request.protect_vocal_phrases else .18
    head_length = round(context_seconds*SR) if request.protect_vocal_phrases else 0
    gains, voice_gains = {}, {}
    for name, track in tracks.items():
        wave, _ = sf.read(TRACKS / track['id'] / 'audio.wav', dtype='float32', always_2d=True)
        gains[name] = float(np.clip(.16/(np.sqrt(np.mean(wave**2))+1e-8), .5, 2.))
        del wave
        voice, _ = sf.read(stems_folder(track, backends[name])/'vocals.wav', dtype='float32', always_2d=True)
        voice = sosfilt(butter(2, 85, btype='highpass', fs=SR, output='sos'), voice, axis=0).astype(np.float32)
        level = active_rms(voice)*gains[name]
        voice_gains[name] = float(np.clip(.078/max(level, 1e-6), .5, 1.8))
        del voice
    warnings = ['Beat-Eins und Abschnittsgrenzen sind Schätzungen; Gesangsphrasen bitte nach Gehör prüfen.']
    if abs(pitch) > 3:
        warnings.append(f'Track B wird um {pitch:+g} Halbtöne verändert; dabei können hörbare Artefakte entstehen.')
    elapsed = 0.
    def source_timing(section, source):
        begin, end, _, _ = clip_timing(tracks[source], section.start_a if source=='A' else section.start_b,
                                       section.bars, bpms[source], bool(request.bpm_a if source=='A' else request.bpm_b))
        return begin, end
    runs = vocal_runs(sections, lambda section: source_timing(section, section.vocal))
    beds = backing_runs(sections, source_timing)
    voice_cache, bed_cache = {}, {}
    for i, section in enumerate(sections):
        check_cancel(cancel)
        progress(45+int(i/len(sections)*43), f'Abschnitt {i+1}/{len(sections)}: {section.name}')
        length = round(section.bars*240/target*SR)
        tail_length = round(context_seconds*SR)
        def clip(source, stem):
            first_index, count, preceding = beds[i, source, stem]
            first = sections[first_index]
            start = first.start_a if source == 'A' else first.start_b
            intro_bars = 0
            for following in sections[first_index:]:
                if following.effect != 'intro' or intro_bars >= count:
                    break
                intro_bars += min(following.bars, count-intro_bars)
            key = (source, stem, start, count, intro_bars)
            if key not in bed_cache:
                bed_cache[key] = source_clip(tracks[source], stem, start, count, bpms[source], target,
                    pitch if source == 'B' else 0, cancel,
                    manual=bool(request.bpm_a if source=='A' else request.bpm_b), tail_seconds=.18,
                    quality=backends[source], intro_bars=intro_bars)*gains[source]
            offset = round(preceding*240/target*SR)
            return fit(bed_cache[key][offset:offset+length+tail_length].copy(), length+tail_length)
        if section.vocal == 'none':
            vocal = np.zeros((length+tail_length, 2), np.float32)
            head = np.zeros((head_length, 2), np.float32)
        else:
            run_start, run_bars, preceding_bars = runs[i]
            first = sections[run_start]
            source = section.vocal
            start = first.start_a if source=='A' else first.start_b
            key = (source, start, run_bars)
            if key not in voice_cache:
                voice_cache[key] = source_clip(tracks[source], 'vocals', start, run_bars, bpms[source], target,
                    pitch if source=='B' else 0, cancel, manual=bool(request.bpm_a if source=='A' else request.bpm_b),
                    tail_seconds=context_seconds, quality=backends[source], head_seconds=head_length/SR) * gains[source]
            offset = head_length+round(preceding_bars*240/target*SR)
            head = voice_cache[key][offset-head_length:offset].copy()
            vocal = fit(voice_cache[key][offset:offset+length+tail_length].copy(), length+tail_length)
        bed = sum(clip(source, stem) for source, stem in backing_components(section))
        vocal = offset_audio(vocal, section.vocal_offset, target)
        vocal *= voice_gains.get(section.vocal, 1.)
        vocal *= 10**(section.vocal_db/20)
        head *= voice_gains.get(section.vocal, 1.)*10**(section.vocal_db/20)
        bed *= 10**(section.instrumental_db/20)
        heads.append(head)
        tails.append((vocal[length:].copy(), bed[length:].copy()))
        vocal, bed = shape_section(vocal[:length], bed[:length], section.effect, target)
        vocal_parts.append(vocal)
        bed_parts.append(bed)
        timing = {}
        for source, track in tracks.items():
            used = section.vocal==source or section.instrumental in (source, 'hybrid')
            if not used:
                timing[source] = (None, None, None, None)
                continue
            start = section.start_a if source=='A' else section.start_b
            begin, end, _, grid = clip_timing(track, start, section.bars, bpms[source],
                                             bool(request.bpm_a if source=='A' else request.bpm_b))
            tempo = section.bars*240/(end-begin)
            timing[source] = begin, end, tempo, grid
            if abs(target/tempo-1)>.2:
                warning=f'Track {source}: starke Tempoänderung ({tempo:.1f} → {target:g} BPM); natürliche Phrasierung und Klang bitte prüfen.'
                if warning not in warnings: warnings.append(warning)
        report.append({**section.model_dump(), 'timeline_start': round(elapsed, 3),
                       **{f'source_{name.lower()}_{field}': value for name,values in timing.items()
                          for field,value in zip(('snapped','end','bpm','grid'), values)}})
        elapsed += length/SR
    continuations = [False]+[i in runs and runs[i][0] != i for i in range(1, len(sections))]
    bed_continuations = [False]+[backing_components(sections[i-1]) == backing_components(sections[i]) and
        all(beds[i, source, stem][0] != i for source, stem in backing_components(sections[i]))
        for i in range(1, len(sections))]
    vocal_edits = []
    vocals, instrumental = join_parts(vocal_parts, bed_parts, tails, sections, continuations, bed_continuations,
        heads if request.protect_vocal_phrases else None, vocal_edits, handle_seconds)
    del vocal_parts, bed_parts, bed_cache, voice_cache
    vocals, instrumental = mix_space(vocals, instrumental, vocal_gain=1.)
    check_cancel(cancel)
    progress(90, 'Lautheit anpassen und WAV/MP3 exportieren')
    sf.write(folder/'vocals.wav', vocals, SR, subtype='FLOAT')
    sf.write(folder/'instrumental.wav', instrumental, SR, subtype='FLOAT')
    sf.write(folder/'premaster.wav', vocals+instrumental, SR, subtype='FLOAT')
    del vocals, instrumental
    measure = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(folder/'premaster.wav'), '-af',
                              'loudnorm=I=-14:TP=-1.2:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True)
    if measure.returncode:
        raise RuntimeError(measure.stderr[-1000:])
    stats = json.loads(measure.stderr[measure.stderr.rfind('{'):])
    normalization = ('loudnorm=I=-14:TP=-1.2:LRA=11:' + ':'.join([
        f'measured_I={stats["input_i"]}', f'measured_TP={stats["input_tp"]}', f'measured_LRA={stats["input_lra"]}',
        f'measured_thresh={stats["input_thresh"]}', f'offset={stats["target_offset"]}', 'linear=true']))
    check_cancel(cancel)
    run_audio(['ffmpeg', '-v', 'error', '-y', '-i', str(folder/'premaster.wav'), '-af', normalization,
               '-ar', str(SR), '-c:a', 'pcm_s24le', str(folder/'mashup.wav')])
    run_audio(['ffmpeg', '-v', 'error', '-y', '-i', str(folder/'mashup.wav'), '-c:a', 'libmp3lame', '-b:a', '320k', str(folder/'mashup.mp3')])
    check_cancel(cancel)
    result = {'id': job_id, 'name': ('Anfang · V6' if request.preview else 'Arrangement · V6')+(' · RoFormer' if all(v=='hq' for v in backends.values()) else ' · Demucs' if all(v=='standard' for v in backends.values()) else ' · gemischte Stems'), 'duration': round(elapsed, 2),
              'bpm': target, 'pitch_b': pitch, 'engine_version': 6, 'separation': backends, 'track_a': a['name'], 'track_b': b['name'], 'sections': report,
              'warnings': warnings, 'request': request.model_dump(), 'mastering': {'target_lufs': -14, 'target_true_peak_db': -1.2},
              'processing': {'backing': 'sum-before-stretch; continuous source runs', 'pitch': 'Rubber Band high quality',
                             'mix': 'continuous EQ; zero-phase midrange duck; 180 ms release', 'grid_jitter_tolerance_ms': 12,
                             'vocal_phrase_protection': request.protect_vocal_phrases,
                             'intro': 'source-domain bass/drum build; preview starts at arrangement beginning',
                             'vocal_handle_limit_seconds': handle_seconds, 'vocal_edits': vocal_edits},
              'stems_note': 'Zeitlich ausgerichtete Gesangs- und Instrumentalbusse vor Mastering, 32-bit float, 44.1 kHz.'}
    if not request.protect_vocal_phrases:
        result['name'] += ' · ohne Phrasenschutz'
    save_json(folder/'arrangement.json', result)
    with zipfile.ZipFile(folder/'stems.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for filename in ('vocals.wav', 'instrumental.wav', 'arrangement.json'):
            archive.write(folder/filename, filename)
    (folder/'premaster.wav').unlink()
    progress(100, 'Mashup fertig')
    return result
