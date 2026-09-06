import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from studio.storage import ROOT, DATA

URL='http://127.0.0.1:18765'
def healthy():
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=1) as response:
            return json.load(response).get('app') in {'Buckswood auto Mashup', 'Mashup Studio'}
    except Exception:
        return False

if not healthy():
    log=(DATA/'server.log').open('a')
    process=subprocess.Popen([sys.executable,'-m','uvicorn','studio.server:app','--host','127.0.0.1','--port','18765','--no-access-log'],
                             cwd=ROOT,stdout=log,stderr=log,start_new_session=True,env={**os.environ,'MASHUP_DEVICE':'cpu'})
    for _ in range(60):
        if healthy(): break
        if process.poll() is not None:
            raise SystemExit(f'Start fehlgeschlagen. Details: {DATA / "server.log"}')
        time.sleep(.5)
    else:
        raise SystemExit(f'Server antwortet noch nicht. Details: {DATA / "server.log"}')
if '--no-browser' not in sys.argv:
    webbrowser.open(URL)
print(f'Buckswood auto Mashup läuft: {URL}')
