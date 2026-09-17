"""Optional, local SheetSage2 annotations; never modify source audio or beat grids."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from .storage import DATA, ROOT, TRACKS, save_json

VERSION = 1
MODEL_REVISION = 'cd2f39b3b807b81f6e32bbb8ea6011da40f77649'
BASE_REVISION = 'd8ba1c745e733b3908ce6ad16ebeb17ac7600a42'
MODEL = DATA / 'models/sheetsage2'
BASE = DATA / 'models/mert-v2'
PYTHON = DATA / 'score-runtime/bin/python'
CACHE = 'score-profile-v1.json'


def installed():
    try:
        manifest = json.loads((MODEL / 'buckswood-install.json').read_text())
        return (manifest['model_revision'] == MODEL_REVISION and manifest['base_revision'] == BASE_REVISION
                and PYTHON.exists() and all((p / 'model.safetensors').is_file() for p in (MODEL, BASE)))
    except (OSError, ValueError, KeyError):
        return False


def fingerprint(track):
    stat = (TRACKS / track['id'] / 'audio.wav').stat()
    return {'id': track['id'], 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def cached(track):
    try:
        data = json.loads((TRACKS / track['id'] / CACHE).read_text())
        if (data.get('version') == VERSION and data.get('model_revision') == MODEL_REVISION
                and data.get('base_revision') == BASE_REVISION and data.get('source') == fingerprint(track)
                and data.get('complete') is True):
            validate(data)
            return data
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def validate(data):
    try:
        _validate(data)
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('Unvollständige Musikanalyse.') from exc


def _validate(data):
    duration = float(data['duration'])
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError('Ungültige Länge der Musikanalyse.')
    for field in ('chords', 'melody', 'structure'):
        if not isinstance(data[field], list):
            raise ValueError('Ungültige Musikanalyse.')
        previous = -1.
        for row in data[field]:
            start, end = float(row['start']), float(row['end'])
            if not np.isfinite([start, end]).all() or not 0 <= start < end <= duration + .001 or start < previous:
                raise ValueError('Ungültige Zeitmarken in der Musikanalyse.')
            previous = start
            if field == 'structure' and (not isinstance(row['label'], str) or not row['label']):
                raise ValueError('Ungültiger Songabschnitt.')
            if field in ('chords', 'melody'):
                vector = np.asarray(row['chroma'], dtype=float)
                if vector.shape != (12,) or not np.isfinite(vector).all() or (vector < 0).any() or (vector > 1).any():
                    raise ValueError('Ungültige Tonhöhen in der Musikanalyse.')
    if not data['chords'] and not data['structure']:
        raise ValueError('SheetSage2 hat keine verwendbaren Akkorde oder Songabschnitte erkannt.')


def ensure(track, progress, cancel):
    from .engine import Cancelled, check_cancel
    check_cancel(cancel)
    existing = cached(track)
    if existing:
        return existing
    if not installed():
        raise ValueError('SheetSage2 ist noch nicht installiert. scripts/setup_score.sh ausführen.')
    source = fingerprint(track)
    folder = TRACKS / track['id']
    progress(1, f'Akkorde und Songabschnitte erkennen: {track["name"]}')
    with tempfile.TemporaryDirectory(prefix='score-work-', dir=folder) as temporary:
        output = Path(temporary)
        command = [str(PYTHON), '-m', 'scripts.analyze_score', '--input', str(folder / 'audio.wav'),
                   '--output', str(output), '--model', str(MODEL), '--base', str(BASE)]
        env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
               'OMP_NUM_THREADS': '4', 'TOKENIZERS_PARALLELISM': 'false'}
        with (folder / 'score.log').open('w') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                while process.poll() is None:
                    if cancel.wait(1):
                        raise Cancelled('Musikanalyse abgebrochen')
                    try:
                        status = json.loads((output / 'progress.json').read_text())
                        progress(status['percent'], f'{track["name"]}: {status["message"]}')
                    except (OSError, ValueError, KeyError):
                        pass
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        check_cancel(cancel)
        if process.returncode:
            raise RuntimeError('SheetSage2 konnte diesen Song nicht analysieren. Details in score.log.')
        value = json.loads((output / 'profile.json').read_text())
        validate(value)
        if fingerprint(track) != source:
            raise ValueError('Der Song wurde während der Analyse verändert. Bitte erneut starten.')
        value.update(version=VERSION, model_revision=MODEL_REVISION, base_revision=BASE_REVISION,
                     source=source, complete=True)
        # Keep the raw transcription for local inspection, separate from audio.
        for name in ('events.json', 'score.abc', 'transcription.mid'):
            path = output / name
            if path.exists():
                path.replace(folder / ('sheetsage2-' + name))
        check_cancel(cancel)
        save_json(folder / CACHE, value)
    progress(100, 'Akkorde und Songabschnitte gespeichert')
    return value


def enrich(profile, score):
    """Blend predictions only where the separated audio supports their pitch.

    Agreement is an acoustic cross-check, not calibrated model confidence.
    Section changes are soft costs; observed Beat This! bar times stay intact.
    """
    if score is None:
        return profile
    result = copy.deepcopy(profile)
    bars = result['bars']
    counts = {'chord_slots': 0, 'melody_slots': 0, 'structure_boundaries': 0}
    for bar in bars:
        edges = np.linspace(bar['start'], bar['end'], 9)
        for field, feature, weight, counter in (('chords', 'harmony', .25, 'chord_slots'),
                                                ('melody', 'voice', .15, 'melody_slots')):
            values = np.asarray(bar[feature], dtype=float)
            for i, (left, right) in enumerate(zip(edges[:-1], edges[1:])):
                symbolic = np.zeros(12)
                coverage = 0.
                for row in score[field]:
                    overlap = max(0., min(right, row['end']) - max(left, row['start']))
                    if overlap:
                        symbolic += overlap * np.asarray(row['chroma'])
                        coverage += overlap
                norm = np.linalg.norm(symbolic)
                if coverage < .5 * (right-left) or norm < 1e-8:
                    continue
                symbolic /= norm
                agreement = float(values[i] @ symbolic)
                active = bar['activity'][i] > max(.006, profile['voice_reference'] * .25)
                if agreement < .55 or (field == 'melody' and not active):
                    continue
                blend = weight * min(1., (agreement-.55)/.25)
                values[i] = (1-blend)*values[i] + blend*symbolic
                values[i] /= max(np.linalg.norm(values[i]), 1e-8)
                counts[counter] += 1
            bar[feature] = values.tolist()
    if bars:
        starts = np.asarray([b['start'] for b in bars])
        for previous, current in zip(score['structure'], score['structure'][1:]):
            if previous['label'] == current['label'] or abs(previous['end']-current['start']) > .05:
                continue
            index = int(np.argmin(abs(starts-current['start'])))
            bar = bars[index]
            length = bar['end']-bar['start']
            # Require sustained sections and a boundary near an observed downbeat.
            if (abs(bar['start']-current['start']) > length*.3
                    or min(previous['end']-previous['start'], current['end']-current['start']) < length*2):
                continue
            bar['structure'] = max(bar.get('structure', 0.), .65)
            counts['structure_boundaries'] += 1
    result['score_analysis'] = {'model': 'SheetSage2', 'revision': MODEL_REVISION, **counts,
                                'warnings': score.get('warnings', []),
                                'sections': [{k: row[k] for k in ('start', 'end', 'label')} for row in score['structure']]}
    return result
