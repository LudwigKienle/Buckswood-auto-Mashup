"""Local downbeat, vocal-boundary and time-aligned pitch analysis.

These are musical planning heuristics, not lyric understanding or chord labels.
Profiles are cached separately from the original audio and the basic analysis.
"""
import json
import math
import numpy as np
import librosa
from .storage import TRACKS, save_json

VERSION = 1


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
    path = TRACKS / track['id'] / 'musical-profile.json'
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
                     'end_cut': boundary_cost(voice_env, times, end, reference)})
    tempo = float(np.median([240/(b['end']-b['start']) for b in bars if b['regular']]))
    # Longer intervals reduce the model's 20 ms timestamp quantisation error.
    spans = [960/(downbeats[i+4]-downbeats[i]) for i in range(len(downbeats)-4)
             if all(b['regular'] for b in bars[i:i+4])]
    if spans:
        tempo = float(np.median(spans))
    value = {'version': VERSION, 'separation': backend, 'model': grid['model'], 'bpm': round(tempo, 2),
             'voice_reference': reference, 'bars': bars}
    save_json(path, value)
    track.update(bpm=value['bpm'], musical_analysis={'model': grid['model'], 'bars': len(bars), 'version': VERSION})
    save_json(path.parent / 'track.json', track)
    return value


def candidates(profile, count):
    result = []
    bars = profile['bars']
    for i in range(len(bars)-count+1):
        rows = bars[i:i+count]
        if not all(r['regular'] for r in rows):
            continue
        activity = np.concatenate([r['activity'] for r in rows])
        active = activity > max(.006, profile['voice_reference']*.25)
        result.append({'index': i, 'start': rows[0]['start'], 'end': rows[-1]['end'],
                       'cut': .4*rows[0]['cut']+.6*rows[-1]['end_cut'],
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
    return float(np.mean(np.sum(v*h, axis=1)))


def plan(a, b, progress, cancel, fixed_pitch=None):
    from .engine import check_cancel
    profiles = {name: profile(track, progress, cancel) for name, track in [('A', a), ('B', b)]}
    result = coherent_plan(profiles, fixed_pitch, lambda: check_cancel(cancel))
    progress(100, 'Zusammenhängendes Arrangement fertig')
    return result


def coherent_plan(profiles, fixed_pitch=None, check=lambda: None):
    """One pair of themes, consecutive phrases, then an exact thematic return.

    B's backing runs through the singer handover. Only eight bars later does
    A's harmony enter under the continuing B phrase. Lyrics are not interpreted.
    """
    pools = None
    for count in (16, 8):
        half = count//2
        ca = candidates(profiles['A'], count)
        cb = candidates(profiles['B'], count)
        by_b = {v['index']: v for v in cb}
        aa = [v for v in ca if .3 <= v['coverage'] <= .98 and
              v['index']+count+4 <= len(profiles['A']['bars']) and
              all(r['regular'] for r in profiles['A']['bars'][v['index']:v['index']+count+4])]
        bb = [v for v in cb if v['index'] >= 4 and v['index']+2*count+4 <= len(profiles['B']['bars'])
              and v['index']+count in by_b and .3 <= by_b[v['index']+count]['coverage'] <= .98
              and all(r['regular'] for r in profiles['B']['bars'][v['index']-4:v['index']+2*count+4])]
        if aa and bb:
            pools = aa, bb, by_b
            break
    if pools is None:
        raise ValueError('Zu wenige zusammenhängende Takte mit Gesang. Bitte den einfachen Plan oder eigene Einstiege verwenden.')
    aa, bb, by_b = pools
    ranked = []
    shifts = range(-5, 6) if fixed_pitch is None else [int(fixed_pitch)]
    for pitch in shifts:
        check()
        best = None
        for av in aa:
            for bed in bb:
                bv = by_b[bed['index']+count]
                forward = compatibility(av['voice'], bed['harmony'], av['active'], harmony_shift=pitch)
                reverse = compatibility(bv['voice'][half*8:], av['harmony'][half*8:],
                                        bv['active'][half*8:], voice_shift=pitch)
                # Both musical directions and the weakest pairing matter. Avoid
                # selecting a spectacular short fragment inside an unrelated verse.
                match = .65*forward+.35*reverse
                value = match-.12*abs(forward-reverse)-.18*av['cut']-.18*bv['cut']
                value += .035*min(av['coverage'], .75)+.035*min(bv['coverage'], .75)
                value -= .05*abs(bed['intensity']-.8)
                value -= .007*abs(pitch)+.012*max(0, abs(pitch)-3)
                if best is None or value > best[0]:
                    best = value, av, bed, bv, forward, reverse
        ranked.append((best[0], pitch, best))
    ranked.sort(key=lambda row: (row[0], -abs(row[1])), reverse=True)
    _, pitch, (_, av, bed, bv, forward, reverse) = ranked[0]
    ai, bi = av['index'], bed['index']
    def at(source, index):
        return round(profiles[source]['bars'][index]['start'], 3)
    specs = [
        ('Intro', 4, 'none', 'B', ai, bi-4, 'intro'),
        ('Thema A · ganze Passage', count, 'A', 'B', ai, bi, 'normal'),
        ('Antwort B · Einstieg', half, 'B', 'B', ai, bi+count, 'normal'),
        ('Antwort B · Fortsetzung', half, 'B', 'hybrid', ai+half, bi+count+half, 'normal'),
        ('Build · Luft vor dem Drop', 4, 'none', 'hybrid', ai+count, bi+2*count, 'build'),
        ('Drop · Thema A kehrt zurück', count, 'A', 'B', ai, bi, 'drop'),
        ('Outro', 4, 'none', 'B', ai, bi+count, 'outro'),
    ]
    sections = [{'name': title, 'bars': n, 'vocal': vocal, 'instrumental': inst,
                 'start_a': at('A', i), 'start_b': at('B', j), 'effect': effect,
                 'vocal_db': 0, 'instrumental_db': -1, 'vocal_offset': 0}
                for title, n, vocal, inst, i, j, effect in specs]
    margin = ranked[0][0]-ranked[1][0] if len(ranked)>1 else None
    note = (f'Zwei feste Motive mit jeweils {count} fortlaufenden Takten. Beim Einstieg von B bleibt dessen '
            'Begleitung erhalten; die Instrumente von A kommen später hinzu. Das erste Motiv kehrt im Drop zurück. '
            'Gesangspausen und Tonhöhen werden geprüft; Textbedeutung und Akkorde werden nicht sicher erkannt.')
    if margin is not None and margin < .015:
        note += f' Tonhöhe unklar: {pitch:+d} und {ranked[1][1]:+d} Halbtöne bitte vergleichen.'
    return {'sections': sections, 'pitch_b': pitch,
            'target_bpm': round(math.sqrt(profiles['A']['bpm']*profiles['B']['bpm'])),
            'analysis': {'version': 3, 'phrase_bars': count, 'strategy': 'continuous-themes',
                         'bpm_a': profiles['A']['bpm'], 'bpm_b': profiles['B']['bpm'],
                         'themes': {'A': [av['start'], av['end']], 'B': [bv['start'], bv['end']]},
                         'similarity_a_over_b': forward, 'similarity_b_over_a': reverse,
                         'boundary_activity_a': av['cut'], 'boundary_activity_b': bv['cut'],
                         'pitch_candidates': [{'shift': s, 'score': q} for q,s,_ in ranked],
                         'pitch_margin': margin, 'alternative_pitch': ranked[1][1] if len(ranked)>1 else None,
                         'note': note}}
