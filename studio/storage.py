import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('MASHUP_DATA', Path.home() / 'Library/Application Support/Mashup Studio'))
TRACKS = DATA / 'tracks'
EXPORTS = DATA / 'exports'
JOBS = DATA / 'jobs'
for folder in (TRACKS, EXPORTS, JOBS):
    folder.mkdir(parents=True, exist_ok=True)

def save_json(path, value):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def read_track(track_id):
    if not track_id.isalnum() or len(track_id) != 16:
        raise ValueError('Ungültige Track-ID.')
    path = TRACKS / track_id / 'track.json'
    if not path.exists():
        raise ValueError('Track wurde nicht gefunden.')
    return json.loads(path.read_text())

def list_tracks():
    return [json.loads(p.read_text()) for p in sorted(TRACKS.glob('*/track.json'))]
