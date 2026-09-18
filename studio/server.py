import json
import logging
import secrets
import tempfile
import threading
import uuid
import time
from typing import Literal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .storage import ROOT, DATA, TRACKS, EXPORTS, JOBS, list_tracks, read_track, save_json
from .models import RenderRequest, PairRequest, LalalKeyRequest, LalalStartRequest

app = FastAPI(title='Buckswood auto Mashup', version='0.1.0')
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
pool = ThreadPoolExecutor(max_workers=1)
jobs = {}
events = {}
lock = threading.RLock()
token = secrets.token_urlsafe(32)
for path in JOBS.glob('*.json'):
    value = json.loads(path.read_text())
    if value['status'] in ('queued', 'running'):
        value.update(status='interrupted', message='Durch Neustart unterbrochen. Bitte erneut starten.')
        save_json(path, value)
    jobs[value['id']] = value

@app.middleware('http')
async def local_only(request: Request, call_next):
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        if request.headers.get('x-studio-token') != token:
            return JSONResponse({'detail': 'Bitte die lokale Oberfläche neu laden.'}, status_code=403)
    return await call_next(request)

def submit(kind, work):
    job_id = uuid.uuid4().hex
    event = threading.Event()
    with lock:
        jobs[job_id] = {'id': job_id, 'kind': kind, 'status': 'queued', 'progress': 0, 'message': 'Wartet auf Verarbeitung'}
        events[job_id] = event
        save_json(JOBS/f'{job_id}.json', jobs[job_id])
    def update(percent, message):
        with lock:
            jobs[job_id].update(progress=percent, message=message)
            save_json(JOBS/f'{job_id}.json', jobs[job_id])
    def runner():
        from .engine import Cancelled, check_cancel
        try:
            check_cancel(event)
            with lock:
                jobs[job_id]['status'] = 'running'
            result = work(job_id, update, event)
            check_cancel(event)
            with lock:
                jobs[job_id].update(status='done', progress=100, result=result)
        except Cancelled:
            if kind == 'render':
                import shutil
                shutil.rmtree(EXPORTS/job_id, ignore_errors=True)
            with lock:
                jobs[job_id].update(status='cancelled', message='Abgebrochen')
        except Exception as exc:
            logging.exception('Job failed')
            with lock:
                jobs[job_id].update(status='failed', message=str(exc))
        finally:
            with lock:
                save_json(JOBS/f'{job_id}.json', jobs[job_id])
    pool.submit(runner)
    return dict(jobs[job_id])

@app.get('/api/state')
def state():
    exports = [json.loads(p.read_text()) for p in sorted(EXPORTS.glob('*/arrangement.json'), key=lambda p: p.stat().st_mtime, reverse=True)]
    defaults=json.loads((DATA/'project.json').read_text()) if (DATA/'project.json').exists() else {}
    from . import score, lalal
    return {'lalal_configured': lalal.configured(), 'lalal_ready': [t['id'] for t in list_tracks() if lalal.ready(t)], 'score_installed': score.installed(), 'score_ready': [t['id'] for t in list_tracks() if score.cached(t)], 'token': token, 'tracks': list_tracks(), 'exports': exports, 'jobs': list(jobs.values()), 'data_dir': str(DATA), 'defaults':defaults, 'hq_installed': __import__('studio.separation', fromlist=['installed']).installed()}

@app.get('/api/health')
def health():
    return {'app': 'Buckswood auto Mashup', 'ok': True, 'engine_version': 7, 'planner_version': 8}

@app.post('/api/upload')
async def upload(file: UploadFile):
    suffix = Path(file.filename or 'track').suffix.lower()
    if suffix not in {'.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aiff', '.aif'}:
        raise HTTPException(400, 'Bitte WAV, MP3, OGG, FLAC, M4A oder AIFF verwenden.')
    dest = DATA/f'upload-{uuid.uuid4().hex}{suffix}'
    size = 0
    try:
        with dest.open('wb') as out:
            while chunk := await file.read(1024*1024):
                size += len(chunk)
                if size > 512*1024*1024:
                    raise HTTPException(413, 'Die Datei darf höchstens 512 MB groß sein.')
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    name = Path(file.filename or 'Track').stem
    def work(job_id, progress, cancel):
        from .analysis import import_track
        try:
            return import_track(dest, name, progress)
        finally:
            dest.unlink(missing_ok=True)
    return submit('import', work)

@app.post('/api/plan')
def plan(pair: PairRequest):
    from .analysis import auto_plan
    try:
        a, b = read_track(pair.track_a), read_track(pair.track_b)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    save_json(DATA/'project.json',pair.model_dump())
    return {'sections': auto_plan(a, b), 'target_bpm': round((a['bpm']+b['bpm'])/2, 1)}

@app.post('/api/render')
def start_render(request: RenderRequest):
    from .engine import render
    try:
        for track_id in (request.track_a, request.track_b):
            read_track(track_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return submit('render', lambda job_id, progress, cancel: render(request, job_id, progress, cancel))

@app.post('/api/intro-plan')
def intro_plan(request: RenderRequest):
    from .intro import rebuild_intro
    try:
        tracks = {'A': read_track(request.track_a), 'B': read_track(request.track_b)}
        return rebuild_intro(tracks, [s.model_dump() for s in request.sections],
                             {'A': request.bpm_a, 'B': request.bpm_b})
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/quality-plan')
def quality_plan(pair: PairRequest):
    from .quality import plan
    try:
        a, b = read_track(pair.track_a), read_track(pair.track_b)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    def work(job_id, progress, cancel):
        from .separation import installed, separate_hq
        if pair.separation_quality in ('auto', 'hq') and installed():
            current = []
            for i, track in enumerate((a,b)):
                current.append(separate_hq(track, lambda p,m: progress(round(i*20+p*.2),m), cancel))
            return plan(*current, lambda p,m: progress(round(40+p*.6),m), cancel, target_bpm=pair.target_bpm, use_score=pair.use_score, separation_quality=pair.separation_quality)
        return plan(a, b, progress, cancel, target_bpm=pair.target_bpm, use_score=pair.use_score, separation_quality=pair.separation_quality)
    return submit('plan', work)

@app.post('/api/separate-hq')
def separate_pair(pair: PairRequest):
    from .separation import separate_hq
    try:
        tracks = [read_track(t) for t in dict.fromkeys((pair.track_a, pair.track_b))]
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    def work(job_id, progress, cancel):
        result = []
        for i, track in enumerate(tracks):
            result.append(separate_hq(track, lambda p,m: progress(round((i*100+p)/len(tracks)), m), cancel))
        return {'tracks': result}
    return submit('separation', work)

# A quote binds consent to exact source fingerprints and expires in ten minutes.
# Consumed quotes return the same job on duplicate HTTP requests.
lalal_quotes = {}

@app.post('/api/lalal/key')
def lalal_key(request: LalalKeyRequest):
    from . import lalal
    try:
        return {'configured': True, 'minutes_left': lalal.store_key(request.api_key)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/lalal/disconnect')
def lalal_disconnect():
    from . import lalal
    lalal.KEY_FILE.unlink(missing_ok=True)
    return {'configured': lalal.configured()}

@app.post('/api/lalal/quote')
def lalal_quote(pair: PairRequest):
    from . import lalal
    try:
        tracks = [read_track(t) for t in dict.fromkeys((pair.track_a, pair.track_b))]
        estimate = lalal.estimate(tracks)
        estimate['minutes_left'] = lalal.Client().minutes()
        estimate['can_start'] = estimate['minutes_left'] >= estimate['estimated_minutes']
        quote_id = secrets.token_urlsafe(24)
        with lock:
            for old in list(lalal_quotes):
                if lalal_quotes[old]['expires'] < time.monotonic():
                    del lalal_quotes[old]
            lalal_quotes[quote_id] = {'tracks': tracks, 'sources': [lalal.fingerprint(t) for t in tracks],
                                     'expires': time.monotonic()+600, 'job_id': None}
        return {**estimate, 'quote_id': quote_id}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post('/api/lalal/separate')
def lalal_separate(request: LalalStartRequest):
    from . import lalal
    with lock:
        quote = lalal_quotes.get(request.quote_id)
        if not quote or quote['expires'] < time.monotonic():
            raise HTTPException(400, 'Bitte die LALAL.AI-Minuten neu prüfen.')
        if quote['job_id']:
            return dict(jobs[quote['job_id']])
        if any(j['status'] in ('queued', 'running') for j in jobs.values()):
            raise HTTPException(409, 'Bitte den laufenden Auftrag zuerst beenden.')
        tracks = quote['tracks']
        if quote['sources'] != [lalal.fingerprint(t) for t in tracks]:
            raise HTTPException(409, 'Songs wurden geändert. Bitte die Minuten neu prüfen.')
        def work(job_id, progress, cancel):
            needed = lalal.estimate(tracks)['estimated_minutes']
            if needed and lalal.Client().minutes() < needed:
                raise ValueError('Das LALAL.AI-Guthaben reicht für diese Songs nicht aus. Es wurde nichts hochgeladen.')
            result = []
            for i, track in enumerate(tracks):
                result.append(lalal.separate(track, lambda p,m: progress(round((i*100+p)/len(tracks)),m), cancel))
            return {'tracks': result, 'provider': 'lalal'}
        job = submit('separation-lalal', work)
        quote['job_id'] = job['id']
        return job

@app.get('/api/jobs/{job_id}')
def job(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404)
        return dict(jobs[job_id])

@app.post('/api/jobs/{job_id}/cancel')
def cancel(job_id: str):
    if job_id not in events:
        raise HTTPException(404)
    events[job_id].set()
    return {'ok': True}

@app.get('/api/tracks/{track_id}/audio')
def track_audio(track_id: str):
    try:
        read_track(track_id)
    except ValueError:
        raise HTTPException(404)
    return FileResponse(TRACKS/track_id/'audio.wav', media_type='audio/wav')

@app.get('/api/tracks/{track_id}/stems/{stem}')
def stem_audio(track_id: str, stem: str, quality: Literal["auto", "standard", "hq", "lalal"] = "auto"):
    try:
        read_track(track_id)
    except ValueError:
        raise HTTPException(404)
    if stem not in {'vocals', 'drums', 'bass', 'other'}:
        raise HTTPException(404)
    from .separation import stems_folder
    try:
        path = stems_folder(read_track(track_id), quality)/f'{stem}.wav'
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    if not path.exists():
        raise HTTPException(404, 'Stems werden beim ersten Rendern erstellt.')
    return FileResponse(path, media_type='audio/wav')

@app.get('/api/exports/{export_id}/{filename}')
def export_file(export_id: str, filename: str):
    if not export_id.isalnum() or filename not in {'mashup.wav', 'mashup.mp3', 'stems.zip', 'arrangement.json'}:
        raise HTTPException(404)
    path = EXPORTS/export_id/filename
    if not path.exists():
        raise HTTPException(404)
    media = {'wav': 'audio/wav', 'mp3': 'audio/mpeg', 'json': 'application/json', 'zip': 'application/zip'}
    return FileResponse(path, media_type=media[filename.split('.')[-1]], filename=filename)

if (ROOT/'web/dist').exists():
    app.mount('/', StaticFiles(directory=ROOT/'web/dist', html=True), name='web')
