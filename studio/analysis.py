import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import numpy as np
import librosa
import soundfile as sf
from .storage import TRACKS, save_json, read_track
from .upstream import KeyFinder

SR = 44100

def run_audio(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Audio konnte nicht verarbeitet werden: ' + result.stderr[-1500:])
    return result.stdout

def import_track(path, original_name=None, progress=lambda *args: None):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(1024 * 1024):
            digest.update(block)
    track_id = digest.hexdigest()[:16]
    folder = TRACKS / track_id
    folder.mkdir(exist_ok=True)
    if (folder / 'track.json').exists():
        return read_track(track_id)
    probe = json.loads(run_audio(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)]))
    duration = float(probe['format']['duration'])
    if not 10 <= duration <= 1800:
        raise ValueError('Bitte einen Song zwischen 10 Sekunden und 30 Minuten wählen.')
    progress(8, 'Audio wird eingelesen')
    run_audio(['ffmpeg', '-v', 'error', '-y', '-i', str(path), '-vn', '-ar', str(SR), '-ac', '2', '-c:a', 'pcm_f32le', str(folder / 'audio.wav')])
    return analyze_track(track_id, original_name or path.stem, progress)

def analyze_track(track_id, name, progress):
    folder = TRACKS / track_id
    y, sr = librosa.load(folder / 'audio.wav', sr=22050)
    progress(25, 'Tempo und Beat-Raster werden geschätzt')
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=512, trim=False)
    beats = librosa.frames_to_time(frames, sr=sr, hop_length=512)
    bpm = float(np.asarray(tempo).item())
    if bpm < 85:
        bpm *= 2
    if bpm > 175:
        bpm /= 2
    # Find a global constant beat period: regression on rounded local indices drifts
    # over long tracks. Circular concentration remains robust to missed beats.
    interval = 60 / bpm
    if len(beats) > 8:
        candidates = np.arange(bpm*.92, bpm*1.08, .02)
        strengths = np.abs(np.exp(2j*np.pi*beats[None, :]*candidates[:, None]/60).mean(axis=1))
        best = float(candidates[np.argmax(strengths)])
        fine = np.arange(best-.025, best+.025, .001)
        vectors = np.exp(2j*np.pi*beats[None, :]*fine[:, None]/60).mean(axis=1)
        best_index = int(np.argmax(np.abs(vectors)))
        bpm = float(fine[best_index])
        interval = 60/bpm
        phase = float(np.angle(vectors[best_index])/(2*np.pi)*interval) % interval
        error = float(np.median(np.abs((beats - phase + interval / 2) % interval - interval / 2)))
    else:
        phase, error = 0., interval
    grid = np.arange(phase, len(y) / sr, interval)
    # Downbeat is an onset-energy heuristic, not a learned meter detector.
    sampled = np.interp(grid, librosa.frames_to_time(np.arange(len(onset)), sr=sr, hop_length=512), onset)
    scores = [float(np.mean(sampled[i::4])) if len(sampled[i::4]) else 0 for i in range(4)]
    downbeat = phase + int(np.argmax(scores)) * interval
    progress(55, 'Tonart und Energieverlauf werden analysiert')
    # Upstream AutoMashup Krumhansl-Schmuckler estimator, limited to a representative excerpt.
    key_audio = y[int(min(15, len(y)/sr*.1)*sr):int(min(len(y)/sr, 105)*sr)]
    key = KeyFinder(waveform=key_audio, sr=sr)
    energy = librosa.feature.rms(y=y, frame_length=2048, hop_length=2205)[0]
    energy_times = librosa.frames_to_time(np.arange(len(energy)), sr=sr, hop_length=2205)
    starts = np.arange(downbeat, len(y)/sr - 8*4*interval, 8*4*interval)
    candidates = []
    for start in starts:
        selected = energy[(energy_times >= start) & (energy_times < start+8*4*interval)]
        candidates.append({'start': round(float(start), 3), 'energy': round(float(np.mean(selected)), 5)})
    chunks = np.array_split(np.abs(y), 360)
    peaks = np.array([np.max(chunk) if len(chunk) else 0 for chunk in chunks])
    peaks = (peaks / max(float(np.max(peaks)), 1e-8)).round(3).tolist()
    info = {'id': track_id, 'name': name, 'duration': round(len(y)/sr, 3), 'bpm': round(bpm, 2),
            'key': key.key_primary, 'key_alternative': key.key_alt, 'key_correlation': key.best_corr_primary,
            'downbeat': round(downbeat, 4), 'grid_error_ms': round(error*1000, 1),
            'waveform': peaks, 'candidates': candidates, 'separated': (folder/'stems/vocals.wav').exists()}
    save_json(folder / 'track.json', info)
    progress(100, 'Track analysiert')
    return info

def choose_start(track, bars, intensity, later=False):
    valid = [c for c in track['candidates'] if c['start'] + bars*240/c.get('bpm',track['bpm']) <= track['duration']]
    if not valid:
        return track['downbeat']
    values = np.array([c['energy'] for c in valid])
    target = float(np.quantile(values, intensity))
    return min(valid, key=lambda c: abs(c['energy'] - target) + (0.002 if later and c['start'] < track['duration']*.35 else 0))['start']

def profile_stems(track):
    """Refine phrase candidates and local tempo using the separated drums and voice."""
    folder = TRACKS / track['id']
    drums, sr = librosa.load(folder/'stems/drums.wav', sr=22050)
    voice, _ = librosa.load(folder/'stems/vocals.wav', sr=sr)
    grids = []
    for start in range(0, max(1, int(track['duration'])-10), 24):
        excerpt = drums[start*sr:(start+36)*sr]
        onset = librosa.onset.onset_strength(y=excerpt, sr=sr)
        tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr)
        times = librosa.frames_to_time(frames, sr=sr)
        bpm = float(np.asarray(tempo).item())
        if bpm < 80: bpm *= 2
        if bpm > 175: bpm /= 2
        if len(times)<8 or bpm<=0: continue
        candidates = np.arange(bpm*.94, bpm*1.06, .01)
        z = np.exp(2j*np.pi*times[None,:]*candidates[:,None]/60).mean(axis=1)
        index = int(np.argmax(abs(z)))
        bpm = float(candidates[index]); confidence = float(abs(z[index]))
        if confidence < .45: continue
        interval = 60/bpm
        phase = float(np.angle(z[index])/(2*np.pi)*interval) % interval
        grid = np.arange(phase, len(excerpt)/sr, interval)
        sampled = np.interp(grid, librosa.frames_to_time(np.arange(len(onset)),sr=sr),onset)
        down = int(np.argmax([np.mean(sampled[i::4]) for i in range(4)]))
        grids.append({'at': start, 'bpm': round(bpm,3), 'downbeat': round(start+phase+down*interval,4), 'confidence':round(confidence,3)})
    candidates=[]
    for grid in grids:
        for start in np.arange(grid['downbeat'],min(grid['at']+24,track['duration']-10),8*240/grid['bpm']):
            end=min(len(drums),round((start+8*240/grid['bpm'])*sr))
            seg=voice[round(start*sr):end]
            rhythm=drums[round(start*sr):end]
            candidates.append({'start':round(float(start),3),'bpm':grid['bpm'],
                'energy':round(float(np.sqrt(np.mean(rhythm**2))),5),
                'vocal_energy':round(float(np.sqrt(np.mean(seg**2))),5)})
    track.update(local_grids=grids, separated=True)
    if grids and max(g['bpm'] for g in grids)-min(g['bpm'] for g in grids)<4:
        track['bpm']=round(float(np.median([g['bpm'] for g in grids])),2)
    if candidates: track['candidates']=candidates
    save_json(folder/'track.json',track)
    return track

def auto_plan(a, b):
    target=(a['bpm']+b['bpm'])/2
    specs = [('Intro', 8, 'none', 'B', 'intro', .25), ('Vocal A', 16, 'A', 'B', 'normal', .65),
             ('Vocal B', 16, 'B', 'A', 'normal', .7), ('Build', 8, 'A', 'B', 'build', .5),
             ('Drop', 16, 'B', 'hybrid', 'drop', .95), ('Outro', 8, 'none', 'A', 'outro', .3)]
    def choose(track,bars,energy,vocal):
        candidates=track['candidates']
        metric='vocal_energy' if vocal and any('vocal_energy' in c for c in candidates) else 'energy'
        peak=max((c.get(metric,0) for c in candidates),default=0)
        active=[c for c in candidates if c.get(metric,0)>=max(.005,peak*.25)
                and c['start']+bars*240/c.get('bpm',track['bpm'])<=track['duration']]
        if active:
            close=[c for c in active if .87 <= target/c.get('bpm',track['bpm']) <= 1.15]
            candidates=close if len(close)>=2 else active
        track={**track,'candidates':[{**c,'energy':c.get(metric,c['energy'])} for c in candidates]}
        return choose_start(track,bars,energy)
    return [{'name': n, 'bars': bars, 'vocal': v, 'instrumental': inst, 'effect': fx,
             'start_a': choose(a, bars, energy, v=='A'), 'start_b': choose(b, bars, energy, v=='B'),
             'vocal_db': 0, 'instrumental_db': -1, 'vocal_offset': 0}
            for i, (n, bars, v, inst, fx, energy) in enumerate(specs)]
