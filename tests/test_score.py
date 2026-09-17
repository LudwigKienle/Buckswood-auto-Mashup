import copy
import json
import threading
import numpy as np
import pytest
from studio import score


def profile():
    triad = np.zeros(12); triad[[0, 4, 7]] = 1 / np.sqrt(3)
    return {'bpm': 120, 'voice_reference': 1., 'bars': [
        {'start': i*2., 'end': (i+1)*2., 'regular': True, 'cut': 0., 'end_cut': 0.,
         'voice': np.eye(12)[[0]*8].tolist(), 'harmony': [triad.tolist()]*8,
         'activity': [1, 1, 1, 1, 0, 0, 0, 0], 'energy': .1, 'structure': 0.} for i in range(12)]}


def annotations():
    chord = np.zeros(12); chord[[0, 4, 7]] = 1
    return {'duration': 24., 'chords': [{'start': 0., 'end': 24., 'label': 'C:maj', 'chroma': chord.tolist()}],
            'melody': [{'start': 0., 'end': 24., 'chroma': np.eye(12)[0].tolist()}],
            'structure': [{'start': 0., 'end': 8., 'label': 'verse'},
                          {'start': 8., 'end': 24., 'label': 'chorus'}]}


def test_score_never_moves_grid_or_modifies_cached_acoustics():
    acoustic = profile(); original = copy.deepcopy(acoustic)
    enriched = score.enrich(acoustic, annotations())
    assert acoustic == original
    assert [(b['start'], b['end']) for b in enriched['bars']] == [(b['start'], b['end']) for b in acoustic['bars']]
    assert enriched['score_analysis']['chord_slots'] == 96
    assert enriched['score_analysis']['melody_slots'] == 48
    assert enriched['score_analysis']['structure_boundaries'] == 1
    assert enriched['bars'][4]['structure'] == .65
    assert score.enrich(acoustic, None) is acoustic


def test_contradictory_pitches_are_not_used_and_unknown_regions_stay_original():
    acoustic = profile(); data = annotations()
    data['chords'][0].update(end=8., chroma=np.eye(12)[1].tolist())
    data['melody'] = []
    enriched = score.enrich(acoustic, data)
    assert enriched['score_analysis']['chord_slots'] == 0
    assert [b['harmony'] for b in enriched['bars']] == [b['harmony'] for b in acoustic['bars']]


def test_score_changes_features_only_with_acoustic_support():
    acoustic = profile(); data = annotations()
    # A supported C note resolves part of a broad harmonic distribution.
    data['chords'][0]['chroma'] = np.eye(12)[0].tolist()
    enriched = score.enrich(acoustic, data)
    assert enriched['bars'][0]['harmony'][0][0] > acoustic['bars'][0]['harmony'][0][0]
    assert np.linalg.norm(enriched['bars'][0]['harmony'][0]) == pytest.approx(1.)


def test_short_or_off_grid_structure_predictions_do_not_force_phrase_changes():
    acoustic = profile(); data = annotations()
    data['structure'] = [{'start': 0., 'end': 7., 'label': 'verse'}, {'start': 7., 'end': 24., 'label': 'chorus'}]
    assert score.enrich(acoustic, data)['score_analysis']['structure_boundaries'] == 0
    data['structure'] = [{'start': 0., 'end': 2., 'label': 'verse'}, {'start': 2., 'end': 24., 'label': 'chorus'}]
    assert score.enrich(acoustic, data)['score_analysis']['structure_boundaries'] == 0


def test_incomplete_stale_corrupt_and_changed_audio_caches_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(score, 'TRACKS', tmp_path)
    folder = tmp_path/'abc'; folder.mkdir(); (folder/'audio.wav').write_bytes(b'audio')
    track = {'id': 'abc'}
    data = annotations()
    data.update(version=score.VERSION, model_revision=score.MODEL_REVISION, base_revision=score.BASE_REVISION,
                source=score.fingerprint(track), complete=True)
    path = folder/score.CACHE
    path.write_text(json.dumps(data)); assert score.cached(track)
    for field, value in [('complete', False), ('model_revision', 'old'), ('version', -1)]:
        broken = dict(data, **{field: value}); path.write_text(json.dumps(broken))
        assert score.cached(track) is None
    path.write_text(json.dumps(data)); (folder/'audio.wav').write_bytes(b'changed audio')
    assert score.cached(track) is None
    path.write_text('{broken'); assert score.cached(track) is None


@pytest.mark.parametrize('change', ['nan', 'bounds', 'vector', 'order'])
def test_invalid_model_output_cannot_be_published(change):
    data = annotations()
    if change == 'nan': data['chords'][0]['chroma'][0] = float('nan')
    if change == 'bounds': data['chords'][0]['end'] = 25
    if change == 'vector': data['chords'][0]['chroma'] = [1, 2]
    if change == 'order': data['structure'].reverse()
    with pytest.raises(ValueError): score.validate(data)


def test_planner_falls_back_when_model_fails_but_propagates_cancellation(monkeypatch):
    from studio import quality
    from studio.engine import Cancelled
    monkeypatch.setattr(quality, 'profile', lambda *args: profile())
    monkeypatch.setattr(quality, 'coherent_plan', lambda *args: {'analysis': {'note': ''}})
    monkeypatch.setattr(score, 'ensure', lambda *args: (_ for _ in ()).throw(RuntimeError('unavailable')))
    result = quality.plan({}, {}, lambda *a: None, threading.Event(), use_score=True)
    assert len(result['analysis']['score_warnings']) == 2
    monkeypatch.setattr(score, 'ensure', lambda *args: (_ for _ in ()).throw(Cancelled('stop')))
    with pytest.raises(Cancelled): quality.plan({}, {}, lambda *a: None, threading.Event(), use_score=True)


def test_disabling_scores_does_not_start_model(monkeypatch):
    from studio import quality
    monkeypatch.setattr(quality, 'profile', lambda *args: profile())
    monkeypatch.setattr(quality, 'coherent_plan', lambda *args: {'analysis': {'note': ''}})
    monkeypatch.setattr(score, 'ensure', lambda *args: pytest.fail('Model should not run'))
    assert quality.plan({}, {}, lambda *a: None, threading.Event(), use_score=False)['analysis']['score_requested'] is False


def test_cancelled_worker_is_terminated_and_never_publishes_cache(tmp_path, monkeypatch):
    from studio.engine import Cancelled
    folder = tmp_path/'abc'; folder.mkdir(); (folder/'audio.wav').write_bytes(b'audio')
    monkeypatch.setattr(score, 'TRACKS', tmp_path)
    monkeypatch.setattr(score, 'installed', lambda: True)
    class Process:
        returncode = None
        def poll(self): return self.returncode
        def terminate(self): self.returncode = -15
        def wait(self, timeout=None): return self.returncode
    class Cancellation:
        def is_set(self): return False
        def wait(self, seconds): return True
    worker = Process()
    monkeypatch.setattr(score.subprocess, 'Popen', lambda *a, **k: worker)
    with pytest.raises(Cancelled):
        score.ensure({'id': 'abc', 'name': 'test'}, lambda *a: None, Cancellation())
    assert worker.returncode == -15
    assert not (folder/score.CACHE).exists()
    assert not list(folder.glob('score-work-*'))


def test_api_forwards_score_choice_and_target_tempo(monkeypatch):
    from fastapi.testclient import TestClient
    from studio import server, quality, separation
    monkeypatch.setattr(server, 'read_track', lambda id: {'id': id})
    monkeypatch.setattr(server, 'submit', lambda kind, work: work('test', lambda *a: None, threading.Event()))
    monkeypatch.setattr(separation, 'installed', lambda: False)
    monkeypatch.setattr(quality, 'plan', lambda *a, **options: options)
    client = TestClient(server.app)
    token = client.get('/api/state').json()['token']
    response = client.post('/api/quality-plan', json={'track_a':'A', 'track_b':'B', 'target_bpm': 99, 'use_score': False},
                           headers={'x-studio-token': token})
    assert response.status_code == 200
    assert response.json() == {'target_bpm': 99., 'use_score': False}
