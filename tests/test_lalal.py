import json
import threading
import uuid
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from studio import lalal, separation
from studio.storage import TRACKS, save_json

@pytest.fixture
def track():
    t={'id':uuid.uuid4().hex[:16], 'name':'Synthetic test song', 'duration':1.01}
    folder=TRACKS/t['id'];folder.mkdir()
    sf.write(folder/'audio.wav',np.zeros((44541,2)),44100,subtype='FLOAT')
    save_json(folder/'track.json',t)
    return t

@pytest.fixture
def fake_client(monkeypatch):
    class Fake:
        calls=[]
        fail_split=False
        fail_download=False
        task=str(uuid.uuid4())
        source=str(uuid.uuid4())
        def __init__(self,*args): pass
        def minutes(self): return 99
        def post(self,route,payload=None,audio=None):
            self.calls.append((route,payload))
            if route=='upload': return {'id':self.source}
            if route=='split/stem_separator':
                if self.fail_split: raise ValueError('network timeout')
                return {'task_id':self.task}
            if route=='check': return {'result':{self.task:{'status':'success','result':{'tracks':[
                {'label':'vocals','url':'https://d.lalal.ai/vocals'}, {'label':'no_vocals','url':'https://d.lalal.ai/instrumental'}]}}}}
            return {}
        def download(self,url,dest,cancel):
            if self.fail_download: raise ValueError('download timeout')
            sf.write(dest,np.full((44541,2),.1 if dest.stem=='vocals' else .3),44100,subtype='FLOAT')
    monkeypatch.setattr(lalal,'Client',Fake)
    def rhythm(command,*args):
        stage=Path(command[-1]).parent
        dest=stage/'rhythm/htdemucs/instrumental';dest.mkdir(parents=True,exist_ok=True)
        for name,value in [('drums',.05),('bass',.07)]:
            sf.write(dest/f'{name}.wav',np.full((44541,2),value),44100,subtype='FLOAT')
    monkeypatch.setattr(separation,'run_worker',rhythm)
    return Fake


def execute(track,event=None):
    return lalal.separate(track,lambda *args:None,event or threading.Event())


def test_complete_flow_cached_render_and_consistency(track,fake_client):
    execute(track)
    assert lalal.ready(track)
    folder=separation.stems_folder(track,'lalal')
    arrays=[sf.read(folder/f'{s}.wav')[0] for s in ('drums','bass','other')]
    np.testing.assert_allclose(sum(arrays),.3,atol=1e-7)
    assert fake_client.calls[1][0]=='split/stem_separator'
    assert fake_client.calls[1][1]['presets']['stem']=='vocals'
    assert fake_client.calls[-1][0]=='delete'
    before=len(fake_client.calls)
    execute(track)
    assert len(fake_client.calls)==before
    assert lalal.estimate([track])['estimated_minutes']==0
    # Default never selects the paid provider, even with a completed paid cache.
    assert separation.selected_backend(track,'auto')=='standard'


def test_missing_cache_never_starts_cloud(track,fake_client):
    with pytest.raises(ValueError,match='zuerst'):
        separation.selected_backend(track,'lalal')
    assert not fake_client.calls


def test_ambiguous_paid_start_is_not_retried(track,fake_client):
    fake_client.fail_split=True
    with pytest.raises(ValueError): execute(track)
    state=lalal.pending(track)
    assert state['phase']=='submitting' and state['idempotency_key']
    fake_client.fail_split=False
    with pytest.raises(ValueError,match='unbestätigt'): execute(track)
    with pytest.raises(ValueError,match='unbestätigt'): lalal.estimate([track])
    assert sum(route=='split/stem_separator' for route,_ in fake_client.calls)==1


def test_download_failure_resumes_same_paid_task(track,fake_client):
    fake_client.fail_download=True
    with pytest.raises(ValueError): execute(track)
    assert lalal.estimate([track])['tracks'][0]['resume']
    fake_client.fail_download=False
    execute(track)
    assert sum(route=='split/stem_separator' for route,_ in fake_client.calls)==1
    assert sum(route=='upload' for route,_ in fake_client.calls)==1


def test_cancel_requests_remote_cancel(track,fake_client):
    from studio.engine import Cancelled
    stage=TRACKS/track['id']/'lalal-work';stage.mkdir()
    save_json(stage/'request.json',{'source':lalal.fingerprint(track),'source_id':fake_client.source,'task_id':fake_client.task,'phase':'processing'})
    event=threading.Event();event.set()
    with pytest.raises(Cancelled): execute(track,event)
    assert fake_client.calls==[('cancel',{'task_ids':[fake_client.task]})]


def test_reject_misaligned_audio(track):
    stage=TRACKS/track['id']/'invalid';stage.mkdir()
    for s in ('vocals','instrumental'):
        sf.write(stage/f'{s}.wav',np.zeros((100,2)),44100)
    with pytest.raises(ValueError,match='Originals'):
        lalal.validate_audio(stage,TRACKS/track['id']/'audio.wav')


def test_source_change_invalidates_cache(track,fake_client):
    execute(track)
    with (TRACKS/track['id']/'audio.wav').open('ab') as out: out.write(b'x')
    assert not lalal.ready(track)


def test_secure_credentials(tmp_path,monkeypatch,fake_client):
    monkeypatch.setattr(lalal,'KEY_FILE',tmp_path/'credentials/lalal.key')
    monkeypatch.delenv('LALAL_API_KEY',raising=False)
    assert lalal.store_key('test-secret')==99
    assert lalal.KEY_FILE.stat().st_mode&0o777==0o600
    assert lalal.key()=='test-secret'
    assert lalal.configured()


def test_official_wire_protocol_and_secret_redaction(monkeypatch):
    from requests import ConnectionError
    calls=[]
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def json(self):return {'minutes_left':12}
    def post(url,**kw):calls.append((url,kw));return Response()
    monkeypatch.setattr(lalal.requests,'post',post)
    client=lalal.Client('private-key')
    assert client.minutes()==12
    assert calls[0][0]=='https://www.lalal.ai/api/v1/limits/minutes_left/'
    assert calls[0][1]['headers']=={'X-License-Key':'private-key'}
    assert calls[0][1]['allow_redirects'] is False
    def fail(*args,**kwargs):raise ConnectionError('private-key')
    monkeypatch.setattr(lalal.requests,'post',fail)
    with pytest.raises(ValueError) as exc:client.minutes()
    assert 'private-key' not in str(exc.value)


@pytest.mark.parametrize('url',['https://evil.example/file','http://127.0.0.1/file','https://lalal.ai.evil.example/file','https://user:pass@d.lalal.ai/file'])
def test_download_rejects_external_urls(url,tmp_path):
    with pytest.raises(ValueError,match='Download-Adresse'):
        lalal.Client('secret').download(url,tmp_path/'out.wav',threading.Event())


def test_quote_consent_dedup_and_stale_sources(track,fake_client,monkeypatch):
    from studio import server
    client=TestClient(server.app)
    headers={'x-studio-token':server.token}
    monkeypatch.setattr(server,'jobs',{})
    monkeypatch.setattr(server,'lalal_quotes',{})
    submitted=[]
    def submit(kind,work):
        submitted.append(kind)
        job={'id':uuid.uuid4().hex,'status':'done'}
        server.jobs[job['id']]=job
        return job
    monkeypatch.setattr(server,'submit',submit)
    pair={'track_a':track['id'],'track_b':track['id']}
    quote=client.post('/api/lalal/quote',headers=headers,json=pair).json()
    assert len(quote['tracks'])==1
    assert quote['estimated_minutes']>0
    body={'quote_id':quote['quote_id'],'consent':False}
    assert client.post('/api/lalal/separate',headers=headers,json=body).status_code==422
    body['consent']=True
    first=client.post('/api/lalal/separate',headers=headers,json=body)
    second=client.post('/api/lalal/separate',headers=headers,json=body)
    assert first.status_code==200 and first.json()==second.json()
    assert submitted==['separation-lalal']
    quote=client.post('/api/lalal/quote',headers=headers,json=pair).json()
    with (TRACKS/track['id']/'audio.wav').open('ab') as out:out.write(b'x')
    assert client.post('/api/lalal/separate',headers=headers,json={'quote_id':quote['quote_id'],'consent':True}).status_code==409


def test_paid_selection_reaches_planner_without_local_preparation(monkeypatch):
    from studio import server,quality
    monkeypatch.setattr(server,'read_track',lambda id:{'id':id})
    monkeypatch.setattr(server,'submit',lambda kind,work:work('test',lambda *a:None,threading.Event()))
    monkeypatch.setattr(separation,'installed',lambda:True)
    monkeypatch.setattr(separation,'separate_hq',lambda *a:pytest.fail('Must use selected cached provider'))
    monkeypatch.setattr(quality,'plan',lambda *a,**kw:kw)
    client=TestClient(server.app)
    response=client.post('/api/quality-plan',headers={'x-studio-token':server.token},json={
        'track_a':'A','track_b':'B','separation_quality':'lalal','use_score':False})
    assert response.status_code==200
    assert response.json()['separation_quality']=='lalal'


def test_balance_failure_never_uploads(track,fake_client,monkeypatch):
    from studio import server
    monkeypatch.setattr(fake_client,'minutes',lambda self:0)
    monkeypatch.setattr(server,'jobs',{})
    monkeypatch.setattr(server,'lalal_quotes',{})
    monkeypatch.setattr(server,'submit',lambda kind,work:work('test',lambda *a:None,threading.Event()))
    client=TestClient(server.app)
    headers={'x-studio-token':server.token}
    quote=client.post('/api/lalal/quote',headers=headers,json={'track_a':track['id'],'track_b':track['id']}).json()
    assert quote['can_start'] is False
    with pytest.raises(ValueError,match='Guthaben'):
        client.post('/api/lalal/separate',headers=headers,json={'quote_id':quote['quote_id'],'consent':True})
    assert not fake_client.calls


def test_download_upgrades_https_without_credentials(tmp_path,monkeypatch):
    calls=[]
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,*a):yield b'audio'
    def get(url,**kw):calls.append((url,kw));return Response()
    monkeypatch.setattr(lalal.requests,'get',get)
    dest=tmp_path/'stem.wav'
    lalal.Client('secret').download('http://d.lalal.ai/stem',dest,threading.Event())
    assert dest.read_bytes()==b'audio'
    assert calls[0][0]=='https://d.lalal.ai/stem'
    assert 'headers' not in calls[0][1]
    assert calls[0][1]['allow_redirects'] is False
