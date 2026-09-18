import threading
import uuid
import numpy as np
import pytest
import soundfile as sf
from studio import lalal, lalal_full, separation
from studio.storage import TRACKS, save_json

@pytest.fixture
def full_track(monkeypatch):
    track={'id':uuid.uuid4().hex[:16],'name':'Test all instruments','duration':1.01}
    folder=TRACKS/track['id'];folder.mkdir()
    sf.write(folder/'audio.wav',np.full((44541,2),.3),44100,subtype='FLOAT')
    save_json(folder/'track.json',track)
    class Fake:
        calls=[];tasks={};fail_stem=None;fail_download=False
        def __init__(self,*args):pass
        def minutes(self):return 999
        def post(self,route,payload=None,audio=None):
            self.calls.append((route,payload))
            if route=='upload':return {'id':str(uuid.uuid4())}
            if route=='split/stem_separator':
                stem=payload['presets']['stem']
                if stem==self.fail_stem:raise ValueError('timeout')
                id=str(uuid.uuid4());self.tasks[id]=stem
                return {'task_id':id}
            if route=='check':
                id=payload['task_ids'][0];stem=self.tasks[id]
                return {'result':{id:{'status':'success','result':{'tracks':[
                    {'label':stem,'url':f'https://d.lalal.ai/{stem}'},
                    {'label':'no_'+stem,'url':f'https://d.lalal.ai/no_{stem}'}]}}}}
            return {}
        def download(self,url,dest,cancel):
            if self.fail_download:raise ValueError('download timeout')
            sf.write(dest,np.full((44541,2),.2 if dest.stem=='instrumental' else .01),44100,subtype='FLOAT')
    monkeypatch.setattr(lalal,'Client',Fake)
    monkeypatch.setattr(separation,'split_instrumental',lambda *a:pytest.fail('No local split in full LALAL mode'))
    return track,Fake


def run(track):return lalal_full.separate(track,lambda *a:None,threading.Event())


def test_full_instruments_wire_models_files_and_cached_reuse(full_track):
    track,fake=full_track
    assert lalal_full.estimate([track])['estimated_minutes']==.3
    run(track)
    assert lalal.ready(track,'all') and not lalal.ready(track)
    folder=separation.stems_folder(track,'lalal_full')
    assert all((folder/f'{name}.wav').exists() for name in lalal_full.STEMS)
    assert (folder/'instruments.zip').is_file()
    splits=[payload for route,payload in fake.calls if route=='split/stem_separator']
    assert len(splits)==9
    assert [p['presets']['stem'] for p in splits]==['vocals','drum','bass','piano','electric_guitar','acoustic_guitar','synthesizer','strings','wind']
    assert all(p['presets']['splitter']=='phoenix' for p in splits[-3:])
    assert len({p['idempotency_key'] for p in splits})==9
    arrays=[sf.read(folder/f'{name}.wav')[0] for name in ('drums','bass','other')]
    np.testing.assert_allclose(sum(arrays),.2,atol=1e-7)
    before=len(fake.calls);run(track)
    assert len(fake.calls)==before and lalal_full.estimate([track])['estimated_minutes']==0
    assert separation.selected_backend(track,'auto')=='standard'


def test_reuses_paid_vocals_and_never_runs_demucs(full_track):
    track,fake=full_track
    old=TRACKS/track['id']/lalal.FOLDER;old.mkdir()
    for name in ('vocals','instrumental','drums','bass','other'):
        sf.write(old/f'{name}.wav',np.full((44541,2),.05),44100,subtype='FLOAT')
    save_json(old/'separation.json',{'source':lalal.fingerprint(track)})
    assert lalal_full.estimate([track])['tracks'][0]['stem_count']==8
    run(track)
    splits=[p['presets']['stem'] for route,p in fake.calls if route=='split/stem_separator']
    assert len(splits)==8 and 'vocals' not in splits
    np.testing.assert_array_equal(sf.read(old/'vocals.wav')[0],sf.read(TRACKS/track['id']/lalal.FULL_FOLDER/'vocals.wav')[0])


def test_ambiguous_instrument_task_cannot_be_rebilled(full_track):
    track,fake=full_track;fake.fail_stem='bass'
    with pytest.raises(ValueError,match='timeout'):run(track)
    fake.fail_stem=None
    with pytest.raises(ValueError,match='unbestätigt'):run(track)
    with pytest.raises(ValueError,match='unbestätigt'):lalal_full.estimate([track])
    assert sum(route=='split/stem_separator' for route,_ in fake.calls)==3
    assert not lalal.ready(track,'all')


def test_download_resume_reuses_remote_task(full_track):
    track,fake=full_track;fake.fail_download=True
    with pytest.raises(ValueError):run(track)
    estimate=lalal_full.estimate([track])
    assert estimate['tracks'][0]['stem_count']==8
    fake.fail_download=False;run(track)
    assert sum(route=='split/stem_separator' for route,_ in fake.calls)==9
    assert sum(route=='upload' for route,_ in fake.calls)==1


def test_quote_binds_mode_and_all_four_tracks(full_track,monkeypatch):
    from studio import server
    from fastapi.testclient import TestClient
    track,_=full_track
    monkeypatch.setattr(server,'jobs',{})
    monkeypatch.setattr(server,'lalal_quotes',{})
    client=TestClient(server.app);headers={'x-studio-token':server.token}
    data={'track_a':track['id'],'track_b':track['id'],'track_c':track['id'],'track_d':track['id'],'mode':'all'}
    quote=client.post('/api/lalal/quote',json=data,headers=headers).json()
    assert quote['mode']=='all' and quote['estimated_minutes']==.3
    assert len(quote['tracks'])==1
    assert server.lalal_quotes[quote['quote_id']]['mode']=='all'
    assert client.post('/api/lalal/quote',json={**data,'mode':'unknown'},headers=headers).status_code==422


def test_full_selection_does_not_trigger_a_paid_request(full_track):
    track,fake=full_track
    with pytest.raises(ValueError,match='zuerst'):
        separation.selected_backend(track,'lalal_full')
    assert not fake.calls


def test_cancel_on_resume_cancels_existing_remote_instrument(full_track):
    from studio.engine import Cancelled
    track,fake=full_track;fake.fail_download=True
    with pytest.raises(ValueError):run(track)
    pending=lalal_full.pending(track)
    task=pending['tasks']['vocals']['task_id']
    event=threading.Event();event.set()
    with pytest.raises(Cancelled):
        lalal_full.separate(track,lambda *a:None,event)
    assert fake.calls[-1]==('cancel',{'task_ids':[task]})
