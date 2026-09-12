"""Local downbeat, vocal-boundary and time-aligned pitch analysis.

These are musical planning heuristics, not lyric understanding or chord labels.
Profiles are cached separately from the original audio and the basic analysis.
"""
import json
import math
import numpy as np
import librosa
from .storage import TRACKS, save_json
from .phrases import quiet_regions, phrase_boundary, HANDLE_SECONDS, handle_duration
from .intro import choose_intro

VERSION = 3


def ensure_grid(track, progress, cancel):
    from .engine import check_cancel
    path = TRACKS / track['id'] / 'beat-grid.json'
    if path.exists():
        return json.loads(path.read_text())
    check_cancel(cancel)
    progress(20, f'Taktanfänge erkennen: {track["name"]}')
    import torch
    from beat_this.inference import File2Beats
    torch.set_num_threads(4)
    predict = File2Beats(checkpoint_path='final0', device='cpu', dbn=False)
    beats, downbeats = predict(str(path.parent / 'audio.wav'))
    check_cancel(cancel)
    if len(downbeats) < 5:
        raise ValueError('Zu wenige sichere Taktanfänge. Bitte den einfachen Planer verwenden.')
    value = {'model': 'beat-this/final0', 'beats': np.asarray(beats).tolist(),
             'downbeats': np.asarray(downbeats).tolist()}
    save_json(path, value)
    return value


def boundary_cost(envelope, times, at, reference):
    """A continuing syllable has energy on BOTH sides of a cut."""
    before = envelope[(times >= at-.14) & (times < at)]
    after = envelope[(times >= at) & (times < at+.14)]
    if not len(before) or not len(after):
        return 0.
    return float(np.clip(min(np.mean(before), np.mean(after)) / max(reference, 1e-6), 0, 1))


def profile(track, progress, cancel):
    from .engine import separate, check_cancel
    path = TRACKS / track['id'] / 'musical-profile-v3.json'
    from .separation import selected_backend
    backend = selected_backend(track, 'auto')
    if path.exists():
        value = json.loads(path.read_text())
        if value.get('version') == VERSION and value.get('separation', 'standard') == backend:
            return value
    if backend == 'standard':
        separate(track, progress, cancel)
    grid = ensure_grid(track, progress, cancel)
    downbeats = np.array(grid['downbeats'])
    progress(35, f'Gesangspausen und Tonhöhen vergleichen: {track["name"]}')
    sr, hop = 22050, 512
    from .separation import stems_folder
    folder = stems_folder(track, 'auto')
    voice, _ = librosa.load(folder / 'vocals.wav', sr=sr)
    other, _ = librosa.load(folder / 'other.wav', sr=sr)
    bass, _ = librosa.load(folder / 'bass.wav', sr=sr)
    drums, _ = librosa.load(folder / 'drums.wav', sr=sr)
    harmonic = other + bass
    voice_env = librosa.feature.rms(y=voice, frame_length=1024, hop_length=hop)[0]
    drum_env = librosa.feature.rms(y=drums, frame_length=1024, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(voice_env)), sr=sr, hop_length=hop)
    reference = float(np.quantile(voice_env, .8))
    check_cancel(cancel)
    chromas = []
    for signal in (voice, harmonic):
        # Identical tuning reference for both sources; retain their actual relative pitch.
        chroma = librosa.feature.chroma_stft(y=signal, sr=sr, n_fft=4096, hop_length=hop, tuning=0, norm=2)
        chromas.append(chroma)
        check_cancel(cancel)
    # Timbre over several bars helps flag a verse/chorus or singer change.
    # This is a novelty heuristic, not lyric or speaker recognition.
    mfcc = librosa.feature.mfcc(y=voice, sr=sr, n_mfcc=9, n_fft=2048, hop_length=hop)[1:]
    bars = []
    median = float(np.median(np.diff(downbeats)))
    for i, (start, end) in enumerate(zip(downbeats[:-1], downbeats[1:])):
        chunks = np.linspace(start, end, 9)
        features = [[], []]
        activity = []
        for left, right in zip(chunks[:-1], chunks[1:]):
            mask = (times >= left) & (times < right)
            activity.append(float(np.mean(voice_env[mask])) if mask.any() else 0.)
            for k, chroma in enumerate(chromas):
                value = np.mean(chroma[:, mask], axis=1) if mask.any() else np.zeros(12)
                features[k].append((value / max(np.linalg.norm(value), 1e-8)).round(5).tolist())
        mask = (times >= start) & (times < end)
        bars.append({'start': float(start), 'end': float(end), 'regular': bool(abs((end-start)/median-1) < .12),
                     'voice': features[0], 'harmony': features[1], 'activity': activity,
                     'energy': float(np.mean(drum_env[mask])) if mask.any() else 0.,
                     'cut': boundary_cost(voice_env, times, start, reference),
                     'end_cut': boundary_cost(voice_env, times, end, reference),
                     'texture': np.mean(mfcc[:, mask & (voice_env > max(.006, reference*.25))], axis=1).tolist()
                         if np.any(mask & (voice_env > max(.006, reference*.25))) else None})
    add_structure(bars, reference)
    tempo = float(np.median([240/(b['end']-b['start']) for b in bars if b['regular']]))
    # Longer intervals reduce the model's 20 ms timestamp quantisation error.
    spans = [960/(downbeats[i+4]-downbeats[i]) for i in range(len(downbeats)-4)
             if all(b['regular'] for b in bars[i:i+4])]
    if spans:
        tempo = float(np.median(spans))
    value = {'version': VERSION, 'separation': backend, 'model': grid['model'], 'bpm': round(tempo, 2),
             'voice_reference': reference, 'bars': bars,
             'vocal_gaps': quiet_regions(voice_env, times, reference)}
    save_json(path, value)
    track.update(bpm=value['bpm'], musical_analysis={'model': grid['model'], 'bars': len(bars), 'version': VERSION})
    save_json(path.parent / 'track.json', track)
    return value



def add_structure(bars, reference):
    """Mark sustained changes in vocal timbre/activity; ignore isolated syllables."""
    valid = [b['texture'] for b in bars if b.get('texture') is not None]
    if len(valid) < 4:
        for bar in bars:
            bar['structure'] = 0.
        return
    center = np.median(valid, axis=0)
    scale = np.maximum(np.median(abs(np.asarray(valid)-center), axis=0), 4.)
    texture = np.asarray([(np.asarray(b['texture'])-center)/scale if b.get('texture') is not None
                          else np.zeros_like(center) for b in bars])
    activity = np.asarray([np.mean(np.asarray(b['activity']) > max(.006, reference*.25)) for b in bars])
    novelty = np.zeros(len(bars))
    for i in range(2, len(bars)-2):
        before, after = slice(i-2, i), slice(i, i+2)
        distance = np.sqrt(np.mean((texture[before].mean(axis=0)-texture[after].mean(axis=0))**2))
        novelty[i] = .7*min(distance/2., 1.)+.3*abs(activity[before].mean()-activity[after].mean())
    # Only prominent local peaks count. Slow changes and every vowel should not
    # force shorter phrases, and a structure change at the START is appropriate.
    threshold = max(.3, float(np.quantile(novelty, .85)))
    for i, bar in enumerate(bars):
        peak = novelty[i] >= max(novelty[max(0,i-2):i+3])
        bar['structure'] = float(novelty[i]) if peak and novelty[i] >= threshold else 0.

def candidates(profile, count, handle_seconds=HANDLE_SECONDS):
    result = []
    bars = profile['bars']
    for i in range(len(bars)-count+1):
        rows = bars[i:i+count]
        if not all(r['regular'] for r in rows):
            continue
        activity = np.concatenate([r['activity'] for r in rows])
        active = activity > max(.006, profile['voice_reference']*.25)
        if 'vocal_gaps' in profile:
            entry = phrase_boundary(profile['vocal_gaps'], rows[0]['start'], 'start', handle_seconds)
            release = phrase_boundary(profile['vocal_gaps'], rows[-1]['end'], 'end', handle_seconds)
        else:
            entry = {'risk': rows[0]['cut'], 'extension': 0., 'clearance': 0.}
            release = {'risk': rows[-1]['end_cut'], 'extension': 0., 'clearance': 0.}
        result.append({'index': i, 'start': rows[0]['start'], 'end': rows[-1]['end'],
                       'entry': entry, 'release': release,
                       'phrase_risk': .5*max(entry['risk'], release['risk'])+.25*(entry['risk']+release['risk']),
                       'entry_beats': (entry['clearance']-entry['extension'])*profile['bpm']/60,
                       'release_beats': (release['extension']-release['clearance'])*profile['bpm']/60,
                       'cut': .5*max(rows[0]['cut'], rows[-1]['end_cut'])+.25*(rows[0]['cut']+rows[-1]['end_cut']),
                       'internal_change': max((r.get('structure', 0.) for r in rows[1:]), default=0.),
                       'entry_change': rows[0].get('structure', 0.),
                       'voice': np.concatenate([r['voice'] for r in rows]),
                       'harmony': np.concatenate([r['harmony'] for r in rows]),
                       'active': active, 'coverage': float(active.mean()),
                       'energy': float(np.mean([r['energy'] for r in rows]))})
    energies = [r['energy'] for r in result]
    for row in result:
        row['intensity'] = float(np.mean(np.array(energies) <= row['energy']))
    return result


def compatibility(voice, harmony, active, voice_shift=0, harmony_shift=0):
    if np.sum(active) < 2:
        return 0.
    v = np.roll(voice, voice_shift, axis=1)[active]
    h = np.roll(harmony, harmony_shift, axis=1)[active]
    # Average corresponding half-beats, not a whole-song key histogram.
    matches = np.sum(v*h, axis=1)
    return float(.75*np.mean(matches)+.25*np.quantile(matches, .2))


def plan(a, b, progress, cancel, fixed_pitch=None, target_bpm=None):
    from .engine import check_cancel
    profiles = {name: profile(track, progress, cancel) for name, track in [('A', a), ('B', b)]}
    result = coherent_plan(profiles, fixed_pitch, lambda: check_cancel(cancel), target_bpm)
    progress(100, 'Zusammenhängendes Arrangement fertig')
    return result


def coherent_plan(profiles, fixed_pitch=None, check=lambda: None, target_bpm=None):
    """One pair of themes, consecutive phrases, then an exact thematic return.

    B's backing runs through the singer handover. A's harmony enters later on
    a 4-, 8- or 16-bar boundary during B's phrase. Lyrics are not interpreted.
    """
    choices = []
    suggested = round(math.sqrt(profiles['A']['bpm']*profiles['B']['bpm']))
    target = target_bpm or suggested
    for count in (32, 24, 16, 8):
        ca = candidates(profiles['A'], count, handle_duration(target)*target/profiles['A']['bpm'])
        cb = candidates(profiles['B'], count, handle_duration(target)*target/profiles['B']['bpm'])
        by_b = {v['index']: v for v in cb}
        aa = [v for v in ca if .3 <= v['coverage'] <= .98 and
              v['index']+count+4 <= len(profiles['A']['bars']) and
              all(r['regular'] for r in profiles['A']['bars'][v['index']:v['index']+count+4])]
        bb = [v for v in cb if v['index'] >= 4 and v['index']+2*count+4 <= len(profiles['B']['bars'])
              and v['index']+count in by_b and .3 <= by_b[v['index']+count]['coverage'] <= .98
              and all(r['regular'] for r in profiles['B']['bars'][v['index']-4:v['index']+2*count+4])]
        for bed in bb:
            bed['intro'] = choose_intro(profiles['B'], bed['index'])
        if aa and bb:
            choices.append((count, aa, bb, by_b))
    if not choices:
        raise ValueError('Zu wenige zusammenhängende Takte mit Gesang. Bitte den einfachen Plan oder eigene Einstiege verwenden.')
    ranked = []
    shifts = range(-5, 6) if fixed_pitch is None else [int(fixed_pitch)]
    for count, aa, bb, by_b in choices:
        # A 24-bar theme is grouped as 8 + 16, keeping the backing handover
        # on an 8-bar boundary instead of switching after an arbitrary 12.
        handover = 8 if count == 24 else count//2
        for pitch in shifts:
            check()
            best = None
            for av in aa:
                for bed in bb:
                    bv = by_b[bed['index']+count]
                    forward = compatibility(av['voice'], bed['harmony'], av['active'], harmony_shift=pitch)
                    reverse = compatibility(bv['voice'][handover*8:], av['harmony'][handover*8:],
                                            bv['active'][handover*8:], voice_shift=pitch)
                    match = .65*forward+.35*reverse
                    value = match-.12*abs(forward-reverse)-.18*av['cut']-.18*bv['cut']
                    value -= .16*(av['phrase_risk']+bv['phrase_risk'])
                    # Pickups precede a downbeat, releases follow it. Penalize
                    # overlaps at A -> B instead of assuming both will fit.
                    overlap = max(0., av['release_beats']-bv['entry_beats'])
                    value -= .14*min(overlap, 1.5)/1.5
                    value += .035*min(av['coverage'], .75)+.035*min(bv['coverage'], .75)
                    value -= .05*abs(bed['intensity']-.8)
                    value += .08*bed['intro']['score']
                    value -= .012*abs(pitch)+.03*max(0, abs(pitch)-2)+.01*max(0, abs(pitch)-3)
                    value -= .18*(av['internal_change']+bv['internal_change'])
                    value += .025*(av['entry_change']+bv['entry_change'])
                    # Complete longer passages may carry a full song. Duration
                    # is only a small preference; harmony and phrase risks retain
                    # their existing weights. Never loop or pad to hit a target.
                    value += .04 if count >= 16 else 0.
                    duration = (bed['intro']['bars']+3*count+8)*240/target
                    value += .06*max(0., 1-abs(duration-180)/120)
                    if best is None or value > best[0]:
                        best = value, av, bed, bv, forward, reverse
            ranked.append((best[0], pitch, count, best))
    ranked.sort(key=lambda row: (row[0], -abs(row[1]), row[2]), reverse=True)
    _, pitch, count, (_, av, bed, bv, forward, reverse) = ranked[0]
    handover = 8 if count == 24 else count//2
    ai, bi = av['index'], bed['index']
    intro = bed['intro']
    def at(source, index):
        return round(profiles[source]['bars'][index]['start'], 3)
    specs = [
        ('Intro · Motiv aufbauen', intro['bars'], 'none', 'B', ai, intro['index'], 'intro'),
        ('Thema A · ganze Passage', count, 'A', 'B', ai, bi, 'normal'),
        ('Antwort B · Einstieg', handover, 'B', 'B', ai, bi+count, 'normal'),
        ('Antwort B · Fortsetzung', count-handover, 'B', 'hybrid', ai+handover, bi+count+handover, 'normal'),
        ('Build · Luft vor dem Drop', 4, 'none', 'hybrid', ai+count, bi+2*count, 'build'),
        ('Drop · Thema A kehrt zurück', count, 'A', 'B', ai, bi, 'drop'),
        ('Outro', 4, 'none', 'B', ai, bi+count, 'outro'),
    ]
    sections = [{'name': title, 'bars': n, 'vocal': vocal, 'instrumental': inst,
                 'start_a': at('A', i), 'start_b': at('B', j), 'effect': effect,
                 'vocal_db': 0, 'instrumental_db': -1, 'vocal_offset': 0}
                for title, n, vocal, inst, i, j, effect in specs]
    pitch_ranked = []
    for row in ranked:
        if row[1] not in [other[1] for other in pitch_ranked]:
            pitch_ranked.append(row)
    margin = pitch_ranked[0][0]-pitch_ranked[1][0] if len(pitch_ranked)>1 else None
    duration = sum(s['bars'] for s in sections)*240/target
    note = (f'Geplant sind etwa {round(duration)//60}:{round(duration)%60:02d} Minuten bei {target:g} BPM. '
            'Die Länge folgt den passenden Passagen; ungefähr drei Minuten sind eine Orientierung. '
            f'Ein {intro["bars"]}-Takt-Intro führt direkt in die erste Begleitung; Bass und Drums bauen sich auf. '
            f'Zwei feste Motive mit jeweils {count} fortlaufenden Takten. Beim Einstieg von B bleibt dessen '
            'Begleitung erhalten; die Instrumente von A kommen später hinzu. Das erste Motiv kehrt im Drop zurück. '
            'Längere Gesangspausen, Platz für Auftakte und Wortenden sowie Tonhöhen und Klangwechsel werden geprüft. '
            'Textbedeutung, Sprecher und Akkorde werden nicht sicher erkannt.')
    if margin is not None and margin < .015:
        note += f' Tonhöhe unklar: {pitch:+d} und {pitch_ranked[1][1]:+d} Halbtöne bitte vergleichen.'
    return {'sections': sections, 'pitch_b': pitch,
            'target_bpm': suggested,
            'analysis': {'version': 6, 'phrase_bars': count, 'strategy': 'continuous-themes', 'intro': intro,
                         'duration_seconds': round(duration, 2), 'planning_bpm': target, 'duration_policy': 'adaptive-3min',
                         'bpm_a': profiles['A']['bpm'], 'bpm_b': profiles['B']['bpm'],
                         'themes': {'A': [av['start'], av['end']], 'B': [bv['start'], bv['end']]},
                         'similarity_a_over_b': forward, 'similarity_b_over_a': reverse,
                         'boundary_activity_a': av['cut'], 'boundary_activity_b': bv['cut'],
                         'pitch_candidates': [{'shift': s, 'score': q, 'phrase_bars': n} for q,s,n,_ in pitch_ranked],
                         'internal_structure_change': {'A': av['internal_change'], 'B': bv['internal_change']},
                         'phrase_boundaries': {'A': {'start': av['entry'], 'end': av['release']},
                                               'B': {'start': bv['entry'], 'end': bv['release']}},
                         'handover_overlap_beats': max(0., av['release_beats']-bv['entry_beats']),
                         'pitch_margin': margin, 'alternative_pitch': pitch_ranked[1][1] if len(pitch_ranked)>1 else None,
                         'note': note}}
