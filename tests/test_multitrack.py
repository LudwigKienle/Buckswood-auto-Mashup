import threading
import uuid
import numpy as np
import pytest
import soundfile as sf
from studio.models import RenderRequest, Section
from studio.multitrack import add_themes
from studio.quality import coherent_plan
from studio.storage import TRACKS, EXPORTS, save_json
from test_duration import stable_profile


def test_missing_optional_source_is_rejected_and_legacy_pair_works():
    with pytest.raises(ValueError, match='Song ausgewählt'):
        RenderRequest(track_a='a', track_b='b', sections=[Section(name='Guest', vocal='C')])
    assert RenderRequest(track_a='a',track_b='b', sections=[Section(name='Pair')]).track_ids()=={'A':'a','B':'b'}


def test_four_theme_plan_preserves_intro_complete_b_and_return():
    profiles={name:stable_profile(40) for name in 'ABCD'}
    base=coherent_plan({k:profiles[k] for k in 'AB'},fixed_pitch=0)
    originals=list(base['sections'])
    result=add_themes(base,profiles)
    sections=result['sections']
    assert sections[:4]==originals[:4]
    assert sections[-3:]==originals[-3:]
    assert [s['vocal'] for s in sections[4:8]]==['none','C','none','D']
    for i,name in [(5,'C'),(7,'D')]:
        assert sections[i]['bars'] in (8,16)
        assert sections[i]['start_'+name.lower()]>=0
        assert sections[i-1]['start_b']+8==sections[i]['start_b']
    request=RenderRequest(track_a='a',track_b='b',track_c='c',track_d='d',sections=sections)
    assert len(request.sections)==11
    assert result['analysis']['duration_seconds']==pytest.approx(sum(s.bars for s in request.sections)*2,abs=.01)


def test_guest_without_vocals_has_actionable_error():
    profiles={name:stable_profile(30) for name in 'ABC'}
    for row in profiles['C']['bars']:row['activity']=[0]*8
    base=coherent_plan({k:profiles[k] for k in 'AB'},fixed_pitch=0)
    with pytest.raises(ValueError,match='Track C'):
        add_themes(base,profiles)


def test_render_routes_four_sources_and_solo_instrument_with_correct_pitch(monkeypatch):
    from studio import engine
    ids={}
    for name in 'ABCD':
        id=uuid.uuid4().hex[:16];ids[name]=id
        folder=TRACKS/id;folder.mkdir();(folder/'stems').mkdir()
        for stem in ('vocals','drums','bass','other'):
            sf.write(folder/'stems'/f'{stem}.wav',np.full((44100,2),.03),44100,subtype='FLOAT')
        sf.write(folder/'audio.wav',np.full((44100,2),.1),44100,subtype='FLOAT')
        save_json(folder/'track.json',{'id':id,'name':name,'bpm':120,'key':'C major','duration':120,'downbeat':0})
    seen=[]
    def clip(track,stem,start,bars,bpm,target,shift,cancel,**kw):
        seen.append((track['name'],stem,start,shift,kw['quality']))
        n=round((bars*240/target+kw.get('tail_seconds',0)+kw.get('head_seconds',0))*44100)
        t=np.arange(n)/44100
        return np.repeat((.05*np.sin(t*2*np.pi*220))[:,None],2,axis=1).astype('float32')
    monkeypatch.setattr(engine,'source_clip',clip)
    sections=[Section(name='C over D piano',vocal='C',instrumental='D',backing_stem='piano',start_c=10,start_d=20,bars=2),
              Section(name='D over A',vocal='D',instrumental='A',start_d=24,start_a=2,bars=2)]
    req=RenderRequest(**{'track_'+k.lower():v for k,v in ids.items()},sections=sections,
                      bpm_a=120,bpm_b=120,bpm_c=120,bpm_d=120,pitch_c=-2,pitch_d=3,target_bpm=120,separation_quality='standard')
    result=engine.render(req,uuid.uuid4().hex,lambda *a:None,threading.Event())
    assert ('C','vocals',10,-2,'standard') in seen
    assert ('D','piano',20,3,'standard') in seen
    assert ('D','vocals',24,3,'standard') in seen
    assert result['sections'][0]['source_c_snapped']==10
    assert result['sections'][0]['source_d_snapped']==20
    assert result['sections'][0]['source_b_snapped'] is None
    audio,rate=sf.read(EXPORTS/result['id']/'mashup.wav')
    assert np.isfinite(audio).all() and len(audio)/rate==pytest.approx(8,abs=.01)


def test_mastering_parses_ffmpeg_json_followed_by_progress():
    import json
    from studio.engine import loudness_stats
    values={'input_i':'-18.36','input_tp':'-17.28','input_lra':'0.00','input_thresh':'-28.36','target_offset':'0.1'}
    log='[Parsed_loudnorm] '+json.dumps(values)+'\n[out] global headers:0KiB\nsize=N/A time=00:00:08.00 bitrate=N/A'
    assert loudness_stats(log)==values
    with pytest.raises(ValueError,match='keine Lautheitsmessung'):
        loudness_stats('empty ffmpeg output')
    with pytest.raises(ValueError,match='hörbares Audio'):
        loudness_stats(json.dumps({**values,'input_i':'-inf'}))
