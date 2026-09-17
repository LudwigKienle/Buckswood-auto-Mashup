"""Opt-in LALAL.AI v1 vocals; paid requests never run during rendering.

Remote task IDs and idempotency keys survive restarts. An ambiguous split response
is deliberately not retried: the provider only permits key reuse before execution.
"""
import json
import math
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
import requests
from .storage import DATA, TRACKS, read_track, save_json

API = 'https://www.lalal.ai/api/v1/'
FOLDER = 'stems-lalal-v1'
PRESETS = {'stem': 'vocals', 'encoder_format': 'wav', 'dereverb_enabled': False,
           'extraction_level': 'clear_cut'}
KEY_FILE = DATA/'credentials/lalal.key'


def key():
    return (KEY_FILE.read_text().strip() if KEY_FILE.exists() else '') or os.environ.get('LALAL_API_KEY', '').strip()


def configured():
    return bool(key())


def store_key(value):
    value = value.strip()
    if not value or len(value) > 1024 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('Bitte einen gültigen LALAL.AI API-Key eingeben.')
    # Validate before replacing a working credential. No media is uploaded.
    remaining = Client(value).minutes()
    KEY_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = KEY_FILE.with_name(f'.lalal-{uuid.uuid4().hex}')
    try:
        with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
            out.write(value)
        temp.replace(KEY_FILE)
    finally:
        temp.unlink(missing_ok=True)
    return remaining


def fingerprint(track):
    s = (TRACKS/track['id']/'audio.wav').stat()
    return {'id': track['id'], 'bytes': s.st_size, 'mtime_ns': s.st_mtime_ns}


def ready(track):
    folder = TRACKS/track['id']/FOLDER
    try:
        meta = json.loads((folder/'separation.json').read_text())
        return meta.get('source') == fingerprint(track) and all((folder/f'{s}.wav').is_file() for s in ('vocals','drums','bass','other'))
    except (OSError, ValueError):
        return False


class Client:
    def __init__(self, credential=None):
        self.credential = credential or key()
        if not self.credential:
            raise ValueError('Bitte zuerst den LALAL.AI API-Key hinterlegen.')

    def post(self, route, payload=None, audio=None):
        headers = {'X-License-Key': self.credential}
        if audio is not None:
            headers.update({'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename=audio.wav'})
        try:
            with requests.post(API+route+'/', headers=headers, json=payload if audio is None else None,
                               data=audio, timeout=(15, 120), allow_redirects=False) as response:
                if response.status_code != 200:
                    messages = {401: 'API-Key abgelehnt.', 403: 'API-Zugang oder Guthaben prüfen.',
                                429: 'Zu viele Anfragen; bitte später fortsetzen.'}
                    raise ValueError('LALAL.AI: '+messages.get(response.status_code, f'Anfrage fehlgeschlagen (HTTP {response.status_code}).'))
                result = response.json()
                if not isinstance(result, dict) or result.get('status') == 'error':
                    raise ValueError('LALAL.AI hat die Anfrage abgelehnt. API-Konto prüfen.')
                return result
        except (requests.RequestException, json.JSONDecodeError):
            # Never expose credential-bearing request objects, URLs, or response text.
            raise ValueError('LALAL.AI ist nicht erreichbar oder lieferte eine ungültige Antwort.') from None

    def minutes(self):
        value = self.post('limits/minutes_left').get('minutes_left')
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('LALAL.AI lieferte kein gültiges Minutenguthaben.')
        return value

    def download(self, url, dest, cancel):
        from .engine import check_cancel
        parsed = urlparse(url)
        # The official example uses http://d.lalal.ai; always upgrade to TLS.
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or not (parsed.hostname == 'lalal.ai' or parsed.hostname.endswith('.lalal.ai')) or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError('Unerwartete LALAL.AI Download-Adresse.')
        url = parsed._replace(scheme='https').geturl()
        temp = dest.with_suffix('.part')
        try:
            # No license key on CDN requests; no redirects to other hosts.
            with requests.get(url, stream=True, timeout=(15, 60), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError('LALAL.AI Download fehlgeschlagen oder abgelaufen.')
                size = 0
                with temp.open('wb') as out:
                    for chunk in response.iter_content(1024*1024):
                        check_cancel(cancel)
                        size += len(chunk)
                        if size > 2*1024**3:
                            raise ValueError('LALAL.AI Download ist unerwartet groß.')
                        out.write(chunk)
            temp.replace(dest)
        except requests.RequestException:
            raise ValueError('LALAL.AI Download unterbrochen. Der Auftrag kann fortgesetzt werden.') from None
        finally:
            temp.unlink(missing_ok=True)


def pending(track):
    path = TRACKS/track['id']/'lalal-work/request.json'
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if value.get('source') != fingerprint(track):
        raise ValueError('Die Quelldatei eines LALAL.AI-Auftrags wurde geändert. Bitte den Song neu importieren.')
    return value


def estimate(tracks):
    rows = []
    for track in tracks:
        cached = ready(track)
        state = {} if cached else pending(track)
        if state.get('phase') == 'submitting':
            raise ValueError('Ein früherer LALAL.AI-Start ist unbestätigt. Bitte den Auftrag im LALAL.AI-Konto prüfen; kein erneuter kostenpflichtiger Start erfolgt.')
        resume = bool(state.get('task_id'))
        rows.append({'id': track['id'], 'name': track['name'], 'cached': cached, 'resume': resume,
                     'minutes': 0 if cached or resume else math.ceil(track['duration'])/60})
    return {'tracks': rows, 'estimated_minutes': math.ceil(sum(r['minutes'] for r in rows)*100)/100}


def separate(track, progress, cancel):
    from .engine import check_cancel, Cancelled
    from .separation import split_instrumental
    if ready(track):
        return read_track(track['id'])
    client = Client()
    folder = TRACKS/track['id']
    stage = folder/'lalal-work'
    stage.mkdir(exist_ok=True)
    path = stage/'request.json'
    state = pending(track) or {'source': fingerprint(track), 'presets': PRESETS}
    try:
        check_cancel(cancel)
        if state.get('phase') == 'submitting':
            raise ValueError('LALAL.AI-Start unbestätigt. Bitte im Anbieter-Konto prüfen; automatischer Neustart gesperrt.')
        if not state.get('source_id'):
            progress(3, f'LALAL.AI: Song hochladen · {track["name"]}')
            with (folder/'audio.wav').open('rb') as audio:
                uploaded = client.post('upload', audio=audio)
            state['source_id'] = str(uuid.UUID(uploaded['id']))
            save_json(path, state)
        check_cancel(cancel)
        if not state.get('task_id'):
            if client.minutes()+1e-6 < math.ceil(track['duration'])/60:
                raise ValueError('Das LALAL.AI Minutenguthaben reicht für diesen Song nicht aus.')
            state.update(phase='submitting', idempotency_key=str(uuid.uuid4()))
            save_json(path, state)  # Durable BEFORE the billable call, even across process crashes.
            task = client.post('split/stem_separator', {'source_id': state['source_id'],
                               'presets': PRESETS, 'idempotency_key': state['idempotency_key']})
            state.update(task_id=str(uuid.UUID(task['task_id'])), phase='processing')
            save_json(path, state)
        if not all((stage/f'{s}.wav').exists() for s in ('vocals','instrumental')):
            deadline = time.monotonic()+3600
            while True:
                check_cancel(cancel)
                result = client.post('check', {'task_ids': [state['task_id']]}).get('result', {}).get(state['task_id'], {})
                status = result.get('status')
                if status == 'success':
                    outputs = {t['label']: t['url'] for t in result['result']['tracks']}
                    for label, name in [('vocals','vocals'),('no_vocals','instrumental')]:
                        if label not in outputs:
                            raise ValueError('LALAL.AI lieferte nicht beide benötigten Spuren.')
                        client.download(outputs[label], stage/f'{name}.wav', cancel)
                    break
                if status != 'progress':
                    raise ValueError('LALAL.AI-Auftrag fehlgeschlagen, abgebrochen oder abgelaufen. Bitte im Anbieter-Konto prüfen. Kein neuer Auftrag wurde berechnet.')
                progress(10+round(max(0,min(100,float(result.get('progress',0))))*.45), f'LALAL.AI trennt Gesang · {track["name"]}')
                if time.monotonic() >= deadline:
                    raise ValueError('LALAL.AI benötigt länger. Erneutes Starten setzt denselben Auftrag fort.')
                cancel.wait(3)
        check_cancel(cancel)
        validate_audio(stage, folder/'audio.wav')
        progress(67, f'Drums und Bass lokal aus der Begleitung trennen · {track["name"]}')
        split_instrumental(stage, folder/'lalal-rhythm.log', cancel, progress)
        save_json(stage/'separation.json', {'version':1, 'provider':'LALAL.AI', 'presets':PRESETS,
                  'source':fingerprint(track), 'stage2':'htdemucs', 'consistency':'other = instrumental - drums - bass'})
        check_cancel(cancel)
        target = folder/FOLDER
        if target.exists():
            raise ValueError('Ein älterer LALAL.AI-Cache gehört zu einer anderen Quelldatei. Bitte neu importieren.')
        stage.replace(target)
        current = read_track(track['id'])
        current['lalal_separated'] = True
        save_json(folder/'track.json', current)
        # Delete only this source after verified local files exist. CDN may cache for 1h.
        try:
            client.post('delete', {'source_id':state['source_id']})
        except ValueError:
            progress(99, 'Stems gespeichert; Cloud-Löschung fehlgeschlagen. Anbieter-Aufbewahrung gilt.')
            current['lalal_cleanup_warning'] = 'Cloud-Löschung fehlgeschlagen; Dateien laufen beim Anbieter ab.'
            save_json(folder/'track.json', current)
        progress(100, 'LALAL.AI-Stems bereit; erneutes Rendern erfolgt lokal.')
        return current
    except Cancelled:
        if state.get('task_id'):
            try:
                client.post('cancel', {'task_ids':[state['task_id']]})
            except ValueError:
                pass
        raise


def validate_audio(stage, source):
    import numpy as np
    import soundfile as sf
    original = sf.info(source)
    for name in ('vocals','instrumental'):
        audio, sr = sf.read(stage/f'{name}.wav', dtype='float32', always_2d=True)
        if sr != original.samplerate or audio.shape != (original.frames, original.channels) or not np.isfinite(audio).all():
            raise ValueError('LALAL.AI-Spuren passen nicht zur Länge, Kanalzahl oder Samplerate des Originals.')
