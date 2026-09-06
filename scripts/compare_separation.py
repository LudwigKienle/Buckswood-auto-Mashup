"""Export identical passages, with active vocal RMS matched, for human A/B review."""
import json
import argparse
import re
from pathlib import Path
import numpy as np
import soundfile as sf
from studio.engine import active_rms
from studio.storage import DATA, read_track
from studio.separation import stems_folder


def compare(track_id, start, seconds, label):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', label):
        raise ValueError('Label must contain only letters, numbers, underscores or hyphens')
    if not np.isfinite(start) or not np.isfinite(seconds) or start < 0 or seconds <= .024:
        raise ValueError('Start must be non-negative and duration greater than 24 ms')
    track = read_track(track_id)
    folder = DATA/'quality-ab'
    folder.mkdir(exist_ok=True)
    versions = []
    levels = []
    for quality in ('standard', 'hq'):
        with sf.SoundFile(stems_folder(track, quality)/'vocals.wav') as source:
            sr = source.samplerate
            source.seek(round(start*sr))
            audio = source.read(round(seconds*sr), dtype='float32', always_2d=True)
        if len(audio) != round(seconds*sr):
            raise ValueError('A/B excerpt extends beyond the source')
        level = active_rms(audio)
        levels.append(float(level))
        audio *= .1/max(level, 1e-6)
        n = round(.012*sr)
        audio[:n] *= np.linspace(0,1,n)[:,None]
        audio[-n:] *= np.linspace(1,0,n)[:,None]
        versions.append(audio)
    common = min(1., .95/max(float(abs(y).max()) for y in versions))
    versions = [y*common for y in versions]
    for quality, audio in zip(('demucs', 'roformer'), versions):
        sf.write(folder/f'{label}-{quality}.wav', audio, sr, subtype='PCM_24')
    combined = np.concatenate([versions[0], np.zeros((round(.7*sr),2),np.float32),versions[1]])
    sf.write(folder/f'{label}-AB.wav', combined, sr, subtype='PCM_24')
    value = {'source_id': track_id, 'start_seconds': start, 'excerpt_seconds': seconds,
             'order': ['Demucs bisher', '0.7 s Pause', 'RoFormer neu'],
             'matching': 'active RMS; same stereo gain per version, common peak headroom',
             'original_active_rms': levels, 'peak_headroom_gain': common,
             'note': 'Unstretched isolated vocals. Subjective review required; no ground truth stems available.'}
    (folder/f'{label}-AB.json').write_text(json.dumps(value, indent=2, ensure_ascii=False))
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('track_id', help='Track ID from the local library')
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--seconds', type=float, default=16)
    parser.add_argument('--label', default='comparison')
    args = parser.parse_args()
    print(json.dumps(compare(args.track_id, args.start, args.seconds, args.label), indent=2))
