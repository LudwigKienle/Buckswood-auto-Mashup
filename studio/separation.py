"""Versioned two-stage separation; retain the original Demucs stems for A/B."""
import json
import os
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from .storage import DATA, ROOT, TRACKS, save_json, read_track

MODEL = DATA/'models/mel-roformer-kim-vocal-2'
HQ_FOLDER = 'stems-roformer-v1'
STEMS = ('vocals', 'drums', 'bass', 'other')


def ready(track):
    folder = TRACKS/track['id']/HQ_FOLDER
    return (folder/'separation.json').exists() and all((folder/f'{s}.wav').exists() for s in STEMS)


def installed():
    return (DATA/'separation-runtime/bin/python').exists() and all((MODEL/name).exists() for name in ('model.safetensors', 'config.json'))


def selected_backend(track, quality='auto'):
    if quality == 'lalal':
        from .lalal import ready as lalal_ready
        if not lalal_ready(track):
            raise ValueError('Bitte zuerst LALAL.AI-Stems für beide Songs erstellen.')
        return 'lalal'
    if quality == 'hq' and not ready(track):
        raise ValueError('Bitte zuerst die neue Vocal-Trennung für beide Songs erstellen.')
    return 'hq' if quality != 'standard' and ready(track) else 'standard'


def stems_folder(track, quality='auto'):
    backend = selected_backend(track, quality)
    from .lalal import FOLDER
    return TRACKS/track['id']/({'hq':HQ_FOLDER, 'lalal':FOLDER}.get(backend, 'stems'))


def worker_progress(text):
    """Read RoFormer JSON and Demucs' carriage-return tqdm output."""
    for line in reversed(text.splitlines()[-20:]):
        try:
            update = json.loads(line)
            done, total = float(update['done']), float(update['total'])
            if total > 0 and math.isfinite(done) and math.isfinite(total) and done >= 0:
                return min(done/total, 1.), f'{done:g}/{total:g} Audioblöcke'
        except (ValueError, KeyError, TypeError):
            pass
        match = re.search(r'^\s*(\d{1,3})%\|.*\|\s*([\d.]+)/([\d.]+)\s*\[([^]\n]+)\]', line)
        if match:
            done, total = float(match[2]), float(match[3])
            if total > 0 and math.isfinite(done) and math.isfinite(total):
                fraction = min(done/total, 1.)
                return fraction, f'{round(fraction*100)} % der Audiospur verarbeitet'
    return None


def run_worker(command, logpath, cancel, progress, lower, upper, label):
    from .engine import Cancelled
    env = {**os.environ, 'OMP_NUM_THREADS': '6', 'MKL_NUM_THREADS': '6'}
    with logpath.open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, cwd=ROOT, env=env)
        last_update = None
        while process.poll() is None:
            if cancel.wait(1):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise Cancelled('Abgebrochen; bisherige Stems bleiben erhalten')
            update = worker_progress(logpath.read_text(errors='replace'))
            if update is not None and update != last_update:
                fraction, detail = update
                progress(round(lower+(upper-lower)*fraction), f'{label}: {detail}')
                last_update = update
    if process.returncode:
        raise RuntimeError(f'{label} fehlgeschlagen: '+logpath.read_text(errors='replace')[-1600:])

    progress(upper, f'{label}: Trennung abgeschlossen')


def separate_hq(track, progress, cancel):
    from .engine import check_cancel
    if ready(track):
        return read_track(track['id'])
    if not installed():
        raise ValueError('RoFormer ist noch nicht installiert. scripts/setup_hq.sh ausführen.')
    folder = TRACKS/track['id']
    stage = Path(tempfile.mkdtemp(prefix='hq-work-', dir=folder))
    try:
        check_cancel(cancel)
        progress(2, f'RoFormer: Gesang isolieren · {track["name"]}')
        run_worker([str(DATA/'separation-runtime/bin/python'), '-m', 'scripts.separate_mlx',
                    '--input', str(folder/'audio.wav'), '--output', str(stage), '--model', str(MODEL)],
                   folder/'roformer.log', cancel, progress, 2, 65, 'RoFormer')
        check_cancel(cancel)
        progress(67, f'Bereinigte Begleitung in Drums, Bass und Instrumente aufteilen · {track["name"]}')
        split_instrumental(stage, folder/'hq-rhythm.log', cancel, progress)
        metadata = json.loads((stage/'separation.json').read_text())
        metadata.update(version=1, stage2='htdemucs: instrumental residual; overlap=0.5',
                        consistency='other = instrumental - drums - bass',
                        source_id=track['id'])
        save_json(stage/'separation.json', metadata)
        target = folder/HQ_FOLDER
        stage.replace(target)
        current = read_track(track['id'])
        current.update(hq_separated=True, hq_model='Mel-Band RoFormer · Kim Vocal 2')
        save_json(folder/'track.json', current)
        progress(100, 'Neue Stems fertig; Originaltrennung weiterhin verfügbar')
        return current
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def split_instrumental(stage, logpath, cancel, progress):
    from .engine import check_cancel
    run_worker([sys.executable, '-m', 'demucs', '-n', 'htdemucs', '-d', 'cpu',
                '--shifts', '1', '--overlap', '.5', '--float32', '-j', '1',
                '-o', str(stage/'rhythm'), str(stage/'instrumental.wav')],
               logpath, cancel, progress, 67, 95, 'Instrumente')
    check_cancel(cancel)
    rhythm = stage/'rhythm/htdemucs/instrumental'
    instrumental, sr = sf.read(stage/'instrumental.wav', dtype='float32', always_2d=True)
    drums, _ = sf.read(rhythm/'drums.wav', dtype='float32', always_2d=True)
    bass, _ = sf.read(rhythm/'bass.wav', dtype='float32', always_2d=True)
    if drums.shape != instrumental.shape or bass.shape != instrumental.shape:
        raise ValueError('Instrumentalspuren haben unterschiedliche Längen.')
    other = instrumental-drums-bass
    for name, audio in [('drums', drums), ('bass', bass), ('other', other)]:
        if not np.isfinite(audio).all():
            raise ValueError('Ungültige Werte in der Trennung.')
        sf.write(stage/f'{name}.wav', audio, sr, subtype='FLOAT')
    shutil.rmtree(stage/'rhythm')
