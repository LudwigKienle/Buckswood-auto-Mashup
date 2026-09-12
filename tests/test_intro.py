import json
import threading
import numpy as np
import pytest
import soundfile as sf
from studio.intro import choose_intro, rebuild_intro, preview_sections, lead_in
from studio.models import Section
from studio.analysis import auto_plan, SR


def track():
    return {'bpm':120, 'downbeat':0, 'duration':200, 'candidates':[
        {'start':32., 'energy':.2}, {'start':64., 'energy':.3}, {'start':112., 'energy':.05}]}


def test_preview_starts_at_the_actual_intro_and_keeps_section_order():
    original = [Section(name='Intro', bars=8, vocal='none', effect='intro'),
                Section(name='A', bars=16), Section(name='B', bars=16, vocal='B')]
    result = preview_sections(original)
    assert [s.name for s in result] == ['Intro', 'A', 'B']
    assert [s.bars for s in result] == [8, 16, 8]
    assert original[-1].bars == 16
    assert preview_sections(original[:1])[0].vocal == 'none'


def test_simple_plan_intro_connects_to_the_first_backing_not_an_unrelated_quiet_excerpt():
    plan = auto_plan(track(), track())
    assert plan[0]['effect'] == 'intro' and plan[0]['vocal'] == 'none'
    assert plan[0]['start_b']+plan[0]['bars']*2 == plan[1]['start_b']


def test_rebuilding_intro_keeps_the_rest_of_the_arrangement_and_uses_its_backing():
    sections = [Section(name='Old intro', effect='intro', start_b=100).model_dump(),
                Section(name='Verse', bars=16, instrumental='A', start_a=40, vocal_db=-2).model_dump(),
                Section(name='Drop', effect='drop', start_a=80).model_dump()]
    result = rebuild_intro({'A':track(), 'B':track()}, sections)
    assert result['sections'][1:] == sections[1:]
    assert result['sections'][0]['instrumental'] == 'A'
    assert result['sections'][0]['start_a'] == 24
    assert sections[0]['start_b'] == 100


def test_song_beginning_previews_the_upcoming_motif_without_negative_source_time():
    lead = lead_in(track(), 0)
    assert lead['strategy'] == 'motif-preview'
    assert lead['start'] == 0 and lead['bars'] == 4
    assert lead_in(track(), 40, manual_bpm=100)['start'] == pytest.approx(21)


def test_intro_choice_prefers_a_real_build_over_an_earlier_full_energy_section():
    def profile(energies):
        return {'bars':[{'start':i*2, 'end':(i+1)*2, 'energy':e, 'regular':True} for i,e in enumerate(energies)]}
    assert choose_intro(profile([.1]*20), 16)['bars'] == 8
    candidate = choose_intro(profile([1.]*8+[1.2,1.2,1.1,.9,.2,.3,.5,.7]+[1.]*4), 16)
    assert candidate['bars'] == 4
    assert candidate['end'] == 32 and candidate['start'] == 24


def test_observed_lead_in_ends_exactly_at_the_selected_neural_downbeat(tmp_path, monkeypatch):
    import studio.intro as intro
    folder = tmp_path/'abc';folder.mkdir()
    grid = (np.arange(30)*2+.12).tolist()
    (folder/'beat-grid.json').write_text(json.dumps({'downbeats':grid}))
    monkeypatch.setattr(intro, 'TRACKS', tmp_path)
    lead = lead_in({**track(), 'id':'abc'}, 24.2)
    assert lead['start'] == 8.12 and lead['end'] == 24.12


def test_intro_reveals_rhythm_before_stretch_and_preserves_the_following_backing(tmp_path, monkeypatch):
    from studio import engine, separation
    folder = tmp_path/'abc'/'stems';folder.mkdir(parents=True)
    t = np.arange(8*SR)/SR
    stereo = lambda x: np.stack([x,x*.5],axis=1).astype('float32')
    drums = stereo(.03*np.sin(2*np.pi*240*t))
    bass = stereo(.04*np.sin(2*np.pi*60*t))
    other = stereo(.05*np.sin(2*np.pi*800*t))
    original = drums+bass+other
    for name,wave in [('drums',drums),('bass',bass),('other',other),('instrumental',original)]:
        sf.write(folder/(name+'.wav'),wave,SR,subtype='FLOAT')
    monkeypatch.setattr(engine,'TRACKS',tmp_path)
    monkeypatch.setattr(separation,'TRACKS',tmp_path)
    result = engine.source_clip({'id':'abc','name':'test','downbeat':0},'instrumental',2,2,
        120,120,0,threading.Event(),quality='standard',intro_bars=1)
    n = round(.15*SR)
    expected = other[2*SR:2*SR+n]+.12*drums[2*SR:2*SR+n]+.2*bass[2*SR:2*SR+n]
    np.testing.assert_allclose(result[:n],expected,atol=2e-8)
    np.testing.assert_array_equal(result[2*SR:],original[4*SR:6*SR])
    np.testing.assert_allclose(result[:,1],result[:,0]*.5,atol=1e-7)


def test_intro_endpoint_requires_local_token_and_preserves_following_sections(monkeypatch):
    from fastapi.testclient import TestClient
    import studio.server as server
    monkeypatch.setattr(server,'read_track',lambda id:track())
    client=TestClient(server.app)
    payload={'track_a':'a','track_b':'b','sections':[Section(name='Verse',bars=16,start_b=40).model_dump()]}
    assert client.post('/api/intro-plan',json=payload).status_code == 403
    token=client.get('/api/state').json()['token']
    response=client.post('/api/intro-plan',json=payload,headers={'x-studio-token':token})
    assert response.status_code == 200
    assert response.json()['sections'][1:] == payload['sections']
