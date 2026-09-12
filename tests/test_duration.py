import threading
import pytest
from studio.models import PairRequest, RenderRequest
from studio.quality import coherent_plan
from test_structure import fixture


def stable_profile(length=80):
    profile = fixture()
    bar = profile['bars'][0]
    profile['bars'] = [{**bar, 'start':i*2., 'end':(i+1)*2.} for i in range(length)]
    return profile


@pytest.mark.parametrize(('tempo', 'theme_bars'), [(90, 16), (120, 24), (150, 32)])
def test_full_song_duration_follows_output_tempo_and_keeps_source_passages_intact(tempo, theme_bars):
    profiles = {'A':stable_profile(), 'B':stable_profile()}
    result = coherent_plan(profiles, fixed_pitch=0, target_bpm=tempo)
    sections = result['sections']
    analysis = result['analysis']
    duration = sum(s['bars'] for s in sections)*240/tempo
    assert 165 <= duration <= 190
    assert analysis['duration_seconds'] == pytest.approx(duration, abs=.01)
    assert analysis['phrase_bars'] == theme_bars
    assert analysis['planning_bpm'] == tempo
    assert result['target_bpm'] == 120  # Suggested tempo remains a separate recommendation.
    request = RenderRequest(track_a='a', track_b='b', target_bpm=tempo, sections=sections)
    assert len(request.sections) == 7
    # The only thematic return is the existing drop. More duration comes from
    # contiguous source music, with the same A -> B handover as the compact form.
    intro, a, b1, b2, build, drop, outro = sections
    assert b1['bars']+b2['bars'] == theme_bars
    assert b1['bars'] in (4, 8, 16)
    assert b1['start_b'] == a['start_b']+a['bars']*2
    assert b2['start_b'] == b1['start_b']+b1['bars']*2
    assert build['start_b'] == b2['start_b']+b2['bars']*2
    for s in sections:
        sources = {'A', 'B'} if s['instrumental'] == 'hybrid' else {s['instrumental']}
        if s['vocal'] != 'none': sources.add(s['vocal'])
        for source in sources:
            assert s['start_'+source.lower()]+s['bars']*2 <= profiles[source]['bars'][-1]['end']


def test_short_sources_stay_short_instead_of_getting_padded_to_three_minutes():
    result = coherent_plan({'A':stable_profile(28), 'B':stable_profile(28)}, fixed_pitch=0)
    assert result['analysis']['phrase_bars'] == 8
    assert result['analysis']['duration_seconds'] < 100
    assert len(result['sections']) == 7


def test_quality_endpoint_passes_the_chosen_tempo_to_duration_planning(monkeypatch):
    from fastapi.testclient import TestClient
    from studio import server, quality, separation
    monkeypatch.setattr(server, 'read_track', lambda id: {'id':id})
    monkeypatch.setattr(separation, 'installed', lambda:False)
    monkeypatch.setattr(quality, 'plan', lambda a,b,progress,cancel,**kw: {'planning_bpm':kw['target_bpm']})
    monkeypatch.setattr(server, 'submit', lambda kind,work:work('test', lambda *args:None, threading.Event()))
    client = TestClient(server.app)
    token = client.get('/api/state').json()['token']
    response = client.post('/api/quality-plan', json={'track_a':'a','track_b':'b','target_bpm':150},
                           headers={'x-studio-token':token})
    assert response.status_code == 200
    assert response.json()['planning_bpm'] == 150
    assert PairRequest(track_a='a',track_b='b').target_bpm is None


@pytest.mark.parametrize('tempo', [0, 201, float('nan')])
def test_planning_rejects_invalid_output_tempo(tempo):
    with pytest.raises(ValueError):
        PairRequest(track_a='a',track_b='b',target_bpm=tempo)
