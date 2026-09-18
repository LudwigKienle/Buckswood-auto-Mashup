"""Nine explicit stem extractions; durable per-stem billing and resumable downloads.

The official multistem endpoint supports only six types. Synth, strings and wind
require the single-stem Phoenix endpoint. Never run this module from a renderer.
"""
import json
import math
import shutil
import time
import uuid
import zipfile
import numpy as np
import soundfile as sf
from .storage import TRACKS, save_json, read_track
from . import lalal

STEMS = {'vocals': 'Gesang', 'drums': 'Drums', 'bass': 'Bass', 'piano': 'Klavier',
         'electric_guitar': 'E-Gitarre', 'acoustic_guitar': 'Akustische Gitarre',
         'synthesizer': 'Synthesizer', 'strings': 'Streicher', 'wind': 'Bläser'}
WORK = 'lalal-all-work'


def pending(track):
    path = TRACKS/track['id']/WORK/'request.json'
    if not path.exists():
        return {'source': lalal.fingerprint(track), 'tasks': {}}
    state = json.loads(path.read_text())
    if state.get('source') != lalal.fingerprint(track):
        raise ValueError('Die Quelle der Instrument-Trennung wurde geändert. Bitte neu importieren.')
    if any(t.get('phase') == 'submitting' for t in state['tasks'].values()):
        raise ValueError('Ein LALAL.AI-Instrumentenstart ist unbestätigt. Bitte im Anbieter-Konto prüfen; kein erneuter kostenpflichtiger Start erfolgt.')
    return state


def estimate(tracks):
    rows = []
    for track in tracks:
        cached = lalal.ready(track, 'all')
        state = {'tasks': {}} if cached else pending(track)
        reuse_vocals = lalal.ready(track)
        needed = [s for s in STEMS if not cached and not state['tasks'].get(s, {}).get('task_id')
                  and not (s == 'vocals' and reuse_vocals)]
        rows.append({'id': track['id'], 'name': track['name'], 'cached': cached,
                     'resume': bool(state['tasks']), 'stem_count': len(needed),
                     'minutes': math.ceil(track['duration'])/60*len(needed)})
    return {'mode': 'all', 'tracks': rows, 'estimated_minutes': math.ceil(sum(r['minutes'] for r in rows)*100)/100}


def presets(name):
    return {**lalal.PRESETS, 'stem': 'drum' if name == 'drums' else name,
            **({'splitter': 'phoenix'} if name in ('synthesizer', 'strings', 'wind') else {})}


def assemble(stage, source):
    """Keep direct instrumental intact; residual cancels drum/bass leakage on sum."""
    lalal.validate_audio(stage, source, tuple(STEMS)+('instrumental',))
    instrumental, rate = sf.read(stage/'instrumental.wav', dtype='float32', always_2d=True)
    for name in ('drums', 'bass'):
        audio, _ = sf.read(stage/f'{name}.wav', dtype='float32', always_2d=True)
        instrumental -= audio
    if not np.isfinite(instrumental).all():
        raise ValueError('Ungültige Werte in der rekonstruierten Begleitung.')
    sf.write(stage/'other.wav', instrumental, rate, subtype='FLOAT')
    with zipfile.ZipFile(stage/'instruments.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name in (*STEMS, 'instrumental', 'other'):
            archive.write(stage/f'{name}.wav', f'{name}.wav')


def separate(track, progress, cancel):
    from .engine import check_cancel, Cancelled
    if lalal.ready(track, 'all'):
        return read_track(track['id'])
    folder = TRACKS/track['id']
    stage = folder/WORK
    stage.mkdir(exist_ok=True)
    path = stage/'request.json'
    state = pending(track)
    client = lalal.Client()
    # Reuse the verified, already-paid vocal/instrumental pair when available.
    if lalal.ready(track) and 'vocals' not in state['tasks']:
        for name in ('vocals', 'instrumental'):
            shutil.copyfile(folder/lalal.FOLDER/f'{name}.wav', stage/f'{name}.wav')
        state['tasks']['vocals'] = {'phase': 'reused'}
        save_json(path, state)
    active_task = None
    try:
        check_cancel(cancel)
        if not state.get('source_id'):
            progress(2, f'LALAL.AI: Song für Instrumententrennung hochladen · {track["name"]}')
            with (folder/'audio.wav').open('rb') as audio:
                uploaded = client.post('upload', audio=audio)
            state['source_id'] = str(uuid.UUID(uploaded['id']))
            save_json(path, state)
        for i, (name, label) in enumerate(STEMS.items()):
            check_cancel(cancel)
            progress(round(3+90*i/len(STEMS)), f'LALAL.AI {i+1}/{len(STEMS)} · {label} · {track["name"]}')
            task = state['tasks'].setdefault(name, {})
            outputs = [(name, name)] if name != 'vocals' else [('vocals', 'vocals'), ('no_vocals', 'instrumental')]
            if name == 'drums':
                outputs = [('drum', 'drums')]
            if task.get('phase') in ('done', 'reused') and all((stage/f'{n}.wav').exists() for _, n in outputs):
                continue
            if not task.get('task_id'):
                if client.minutes()+1e-6 < math.ceil(track['duration'])/60:
                    raise ValueError('LALAL.AI-Guthaben reicht nicht für die nächste Instrumentenspur. Fertige Spuren bleiben gespeichert.')
                task.update(phase='submitting', idempotency_key=str(uuid.uuid4()), presets=presets(name))
                save_json(path, state)
                response = client.post('split/stem_separator', {'source_id': state['source_id'],
                    'presets': task['presets'], 'idempotency_key': task['idempotency_key']})
                task.update(task_id=str(uuid.UUID(response['task_id'])), phase='processing')
                save_json(path, state)
            active_task = task['task_id']
            deadline = time.monotonic()+3600
            while True:
                check_cancel(cancel)
                response = client.post('check', {'task_ids': [active_task]}).get('result', {}).get(active_task, {})
                if response.get('status') == 'success':
                    urls = {t['label']: t['url'] for t in response['result']['tracks']}
                    for remote, local in outputs:
                        if remote not in urls:
                            raise ValueError(f'LALAL.AI lieferte die Spur {label} nicht.')
                        if not (stage/f'{local}.wav').exists():
                            client.download(urls[remote], stage/f'{local}.wav', cancel)
                    lalal.validate_audio(stage, folder/'audio.wav', tuple(n for _, n in outputs))
                    task['phase'] = 'done'
                    save_json(path, state)
                    active_task = None
                    break
                if response.get('status') != 'progress':
                    raise ValueError(f'LALAL.AI-Auftrag für {label} fehlgeschlagen oder abgelaufen. Kein automatischer kostenpflichtiger Neustart.')
                progress(round(3+90*(i+float(response.get('progress', 0))/100)/len(STEMS)),
                         f'LALAL.AI {i+1}/{len(STEMS)} · {label} · {track["name"]}')
                if time.monotonic() >= deadline:
                    raise ValueError('LALAL.AI braucht länger. Fortsetzen verwendet denselben Auftrag.')
                cancel.wait(3)
        check_cancel(cancel)
        progress(95, 'Instrumente prüfen und einzeln für den Download speichern')
        assemble(stage, folder/'audio.wav')
        save_json(stage/'separation.json', {'version': 1, 'provider': 'LALAL.AI',
            'source': lalal.fingerprint(track), 'stems': list(STEMS), 'stage2': 'none',
            'consistency': 'other = instrumental - drums - bass; individual instrument estimates may overlap'})
        check_cancel(cancel)
        target = folder/lalal.FULL_FOLDER
        if target.exists():
            raise ValueError('Instrumenten-Cache gehört zu einer anderen Quelle. Bitte neu importieren.')
        stage.replace(target)
        current = read_track(track['id'])
        current['lalal_full_separated'] = True
        save_json(folder/'track.json', current)
        try:
            client.post('delete', {'source_id': state['source_id']})
        except ValueError:
            progress(99, 'Instrumente gespeichert; Cloud-Löschung fehlgeschlagen. Anbieter-Aufbewahrung gilt.')
        progress(100, 'Alle LALAL.AI-Instrumente lokal bereit')
        return current
    except Cancelled:
        for task in state['tasks'].values():
            if task.get('phase') != 'processing' or not task.get('task_id'):
                continue
            try:
                client.post('cancel', {'task_ids': [task['task_id']]})
            except ValueError:
                pass
        raise
