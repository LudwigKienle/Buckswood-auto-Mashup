import json
import threading
import numpy as np
import pytest
from studio.analysis import SR
from studio.quality import boundary_cost, compatibility
from studio.engine import stretch, active_rms, join_parts, clip_timing
from studio.models import Section


def test_continuing_syllable_costs_more_than_pause_or_new_phrase():
    times=np.arange(0,2,.01)
    sustained=np.ones(len(times))*.1
    paused=sustained.copy();paused[(times>.8)&(times<1.1)]=0
    beginning=sustained.copy();beginning[times<1]=0
    assert boundary_cost(sustained,times,1,.1)>.9
    assert boundary_cost(paused,times,1,.1)<.2
    assert boundary_cost(beginning,times,1,.1)==0


def test_harmony_score_checks_sequence_not_only_global_histogram():
    voice=np.eye(12)[[0,4,7,2]]
    wrong=np.roll(voice,1,axis=0)
    active=np.ones(4,dtype=bool)
    assert compatibility(voice,voice,active)>.99
    assert compatibility(voice,wrong,active)<.01
    assert compatibility(voice,np.roll(voice,3,axis=1),active,harmony_shift=-3)>.99


def test_pause_length_does_not_change_active_voice_gain():
    t=np.arange(SR)/SR
    phrase=np.repeat((.1*np.sin(2*np.pi*220*t))[:,None],2,axis=1).astype('float32')
    assert active_rms(phrase)==pytest.approx(active_rms(np.concatenate([phrase,np.zeros((SR*3,2))])),rel=.01)


def test_keyframe_warp_keeps_clicks_on_target_grid_and_duration():
    signal=np.zeros((SR*4,2),np.float32)
    for at in [.2,1.4,2.1,3.3]:
        start=round(at*SR)
        signal[start:start+120,0]=np.hanning(120)*.3
    signal[:,1]=signal[:,0]
    mapping={round(x*SR):round(y*SR) for x,y in zip([0,.2,1.4,2.1,3.3,4],[0,.2,1.2,2.2,3.2,4])}
    result=stretch(signal,1,keyframes=mapping,percussive=True)
    assert abs(len(result)-4*SR)<100
    for expected in [.2,1.2,2.2,3.2]:
        center=round(expected*SR)
        peak=np.argmax(abs(result[center-2200:center+2200,0]))+center-2200
        assert abs(peak-center)<.025*SR


def test_transitions_keep_grid_length_and_do_not_repeat_outgoing_syllables():
    n=SR
    first=np.ones((n,2),np.float32)*.1
    silence=np.zeros_like(first)
    tail=np.zeros((round(.18*SR),2),np.float32)
    sections=[Section(name='A'),Section(name='B')]
    voice,bed=join_parts([first,silence],[first,silence],[(tail,tail),(tail,tail)],sections)
    assert len(voice)==2*n
    assert np.max(abs(voice[n:]))==0
    assert np.isfinite(bed).all()


def test_neural_grid_and_manual_override(tmp_path,monkeypatch):
    monkeypatch.setattr('studio.engine.TRACKS',tmp_path)
    folder=tmp_path/'abc';folder.mkdir()
    (folder/'beat-grid.json').write_text(json.dumps({'downbeats':[.1,2.1,4.12,6.1,8.11]}))
    track={'id':'abc','name':'test','downbeat':0}
    start,end,anchors,kind=clip_timing(track,2.2,2,120)
    assert (start,end,kind)==(2.1,6.1,'beat-this')
    assert len(anchors)==3
    assert clip_timing(track,2.2,2,100,True)[3]=='manual'
    with pytest.raises(ValueError):clip_timing(track,6,4,120)


def test_theme_plan_keeps_voice_continuation_and_backing_at_handover():
    from studio.quality import coherent_plan
    def fixture():
        return {'bpm':120, 'voice_reference':1, 'bars':[
            {'start':i*2.,'end':(i+1)*2.,'regular':True,'cut':.05,'end_cut':.05,
             'voice':np.eye(12)[[0,4,7,0,4,7,0,4]].tolist(),
             'harmony':np.eye(12)[[0,4,7,0,4,7,0,4]].tolist(),
             'activity':[1,1,1,1,0,0,0,0], 'energy':.1} for i in range(80)]}
    result=coherent_plan({'A':fixture(),'B':fixture()})
    intro,a,b1,b2,build,drop,outro=result['sections']
    assert a['bars']==16
    assert b1['vocal']==b2['vocal']=='B'
    assert b2['start_b']==b1['start_b']+b1['bars']*2
    assert a['instrumental']==b1['instrumental']=='B'
    assert b1['start_b']==a['start_b']+a['bars']*2
    assert a['start_b']==intro['start_b']+intro['bars']*2
    assert drop['start_a']==a['start_a'] and drop['start_b']==a['start_b']
    assert build['vocal']=='none'
    assert result['pitch_b']==0


def test_overlap_add_preserves_stereo_edges_and_arbitrary_length():
    from scripts.separate_mlx import overlap_separate
    rng=np.random.default_rng(4)
    for length in (3,801,3197):
        audio=rng.normal(0,.1,(length,2)).astype(np.float32)
        result=overlap_separate(audio,lambda chunk: chunk*.7,800,400)
        np.testing.assert_allclose(result,audio*.7,atol=1e-7)
    with pytest.raises(ValueError):
        overlap_separate(np.ones((900,2)),lambda x:x*np.nan,800,400)


def test_hq_is_never_selected_from_partial_or_failed_results(tmp_path,monkeypatch):
    import studio.separation as sep
    monkeypatch.setattr(sep,'TRACKS',tmp_path)
    track={'id':'abc'}
    folder=tmp_path/'abc'/sep.HQ_FOLDER;folder.mkdir(parents=True)
    for stem in sep.STEMS:(folder/f'{stem}.wav').write_bytes(b'placeholder')
    assert sep.selected_backend(track)=='standard'
    with pytest.raises(ValueError):sep.selected_backend(track,'hq')
    (folder/'separation.json').write_text('{}')
    assert sep.selected_backend(track)=='hq'
    assert sep.selected_backend(track,'standard')=='standard'


def test_vocal_run_survives_instrument_change_but_not_a_source_jump():
    from studio.engine import vocal_runs
    sections=[Section(name='1',vocal='B',instrumental='B',start_b=10,bars=8),
              Section(name='2',vocal='B',instrumental='hybrid',start_b=26,bars=8),
              Section(name='3',vocal='B',start_b=70,bars=8)]
    runs=vocal_runs(sections,lambda s:(s.start_b,s.start_b+s.bars*2))
    assert runs[0]==(0,16,0)
    assert runs[1]==(0,16,8)
    assert runs[2]==(2,8,0)
