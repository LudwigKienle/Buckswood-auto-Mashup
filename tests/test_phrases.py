import threading
import numpy as np
import pytest
import soundfile as sf
from studio.phrases import quiet_regions, phrase_boundary, audio_regions, restore_vocal_edges, handle_duration
from studio.models import Section


def stereo(x):
    return np.repeat(np.asarray(x, dtype=np.float32)[:, None], 2, axis=1)


def test_pause_detector_rejects_short_consonant_gaps_and_scales_with_voice():
    times = np.arange(300)*.01
    levels = np.ones(300)*.1
    levels[40:46] = 0  # 60 ms, inside a word
    levels[100:120] = 0  # 200 ms, usable pause
    gaps = quiet_regions(levels, times, .1)
    assert gaps == [(1., 1.2)]
    assert quiet_regions(levels*.2, times, .02) == gaps


def test_handles_need_bounding_pauses_and_do_not_pull_in_the_next_phrase():
    gaps = [(0., .7), (1.2, 1.6), (2.2, 2.5)]
    assert phrase_boundary(gaps, 1., 'start')['extension'] == pytest.approx(.335)
    assert phrase_boundary(gaps, 1., 'end')['extension'] == pytest.approx(.235)
    assert phrase_boundary(gaps, 1.4, 'end')['extension'] == 0
    assert phrase_boundary([], 1., 'end')['risk'] == 1
    assert phrase_boundary([(0., .1)], 1.5, 'start', limit=.8)['extension'] == 0


def test_vocal_handles_follow_tempo_with_a_hard_duration_cap():
    assert handle_duration(120) == pytest.approx(1.08)
    assert handle_duration(80) == pytest.approx(1.58)
    assert handle_duration(60) == 1.6


def test_stereo_activity_does_not_cancel_opposite_polarity_vocals():
    wave = np.ones(1000, dtype=np.float32)*.1
    assert audio_regions(np.stack([wave, -wave], axis=1), 1000, .1) == []


def test_complete_pickup_and_release_are_restored_without_moving_grid():
    sr = 1000
    silent = stereo(np.zeros(sr))
    phrase = silent.copy(); phrase[:200] = .1; phrase[-200:] = .1
    head = stereo(np.r_[np.zeros(600), np.ones(200)*.1])
    tail = stereo(np.r_[np.ones(200)*.1, np.zeros(600)])
    parts = [silent.copy(), phrase.copy(), silent.copy()]
    voice = np.concatenate(parts)
    sections = [Section(name='intro', vocal='none'), Section(name='voice'), Section(name='outro', vocal='none')]
    edits = restore_vocal_edges(voice, parts, [head]*3, [tail]*3, [False]*3, sections, sr, .1)
    assert [e['status'] for e in edits] == ['restored', 'restored']
    assert len(voice) == 3000
    np.testing.assert_array_equal(voice[1000:2000], phrase)
    np.testing.assert_array_equal(voice[800:1000], head[-200:])
    np.testing.assert_array_equal(voice[2000:2200], tail[:200])
    assert np.max(abs(voice[:700])) == 0
    assert np.max(abs(voice[2300:])) == 0


def test_handles_do_not_overlay_another_singer_or_escape_song_bounds():
    sr = 1000
    voice = stereo(np.ones(2000)*.1)
    parts = [voice[:1000].copy(), voice[1000:].copy()]
    head = stereo(np.r_[np.zeros(600), np.ones(200)*.2])
    tail = stereo(np.r_[np.ones(200)*.2, np.zeros(600)])
    sections = [Section(name='A'), Section(name='B', vocal='B')]
    edits = restore_vocal_edges(voice, parts, [head]*2, [tail]*2, [False]*2, sections, sr, .1)
    assert len(edits) == 4
    assert all(e['status'] == 'no-space' for e in edits)
    assert np.max(voice) <= .1+1e-7
    np.testing.assert_array_equal(voice[10:990], parts[0][10:990])


def test_continuing_phrase_and_manual_offset_keep_their_timing():
    sr = 1000
    voice = stereo(np.ones(2000)*.1)
    parts = [voice[:1000].copy(), voice[1000:].copy()]
    handle = stereo(np.r_[np.zeros(600), np.ones(200)*.2])
    sections = [Section(name='A'), Section(name='B')]
    restore_vocal_edges(voice, parts, [handle]*2, [handle[::-1]]*2, [False, True], sections, sr, .1)
    np.testing.assert_array_equal(voice[990:1010], stereo(np.ones(20)*.1))
    shifted = stereo(np.ones(1000)*.1)
    edits = restore_vocal_edges(shifted, [shifted.copy()], [handle], [handle[::-1]],
        [False], [Section(name='manual', vocal_offset=1)], sr, .1)
    assert edits == []


def test_unbounded_sustain_keeps_short_release_only_into_silence():
    sr = 1000
    phrase, silence = stereo(np.ones(1000)*.1), stereo(np.zeros(1000))
    handle = stereo(np.ones(800)*.1)
    voice = np.concatenate([phrase, silence])
    sections = [Section(name='voice'), Section(name='build', vocal='none')]
    edits = restore_vocal_edges(voice, [phrase, silence], [handle]*2, [handle]*2,
        [False]*2, sections, sr, .1)
    assert edits[-1]['status'] == 'faded-release'
    np.testing.assert_array_equal(voice[900:1000], phrase[900:])
    assert voice[1050, 0] > 0
    assert np.max(abs(voice[1180:])) == 0


def test_bounding_pause_is_verified_beyond_the_allowed_edit_limit():
    sr = 1000
    phrase, silence = stereo(np.ones(1000)*.1), stereo(np.zeros(1500))
    handle = stereo(np.r_[np.ones(760)*.1, np.zeros(240)])
    voice = np.concatenate([phrase, silence])
    sections = [Section(name='voice'), Section(name='build', vocal='none')]
    edits = restore_vocal_edges(voice, [phrase, silence], [handle[::-1]]*2, [handle]*2,
        [False]*2, sections, sr, .1, limit=.8)
    assert edits[-1]['status'] == 'restored'
    assert edits[-1]['seconds'] <= .8
    np.testing.assert_array_equal(voice[1000:1760], handle[:760])


@pytest.mark.parametrize('start', [0., 2.])
def test_source_handles_preserve_original_timing_including_start_of_file(tmp_path, monkeypatch, start):
    from studio import engine, separation
    from studio.analysis import SR
    folder = tmp_path/'abc'/'stems'; folder.mkdir(parents=True)
    rng = np.random.default_rng(8)
    original = rng.normal(0, .03, (SR*6, 2)).astype(np.float32)
    sf.write(folder/'vocals.wav', original, SR, subtype='FLOAT')
    monkeypatch.setattr(engine, 'TRACKS', tmp_path)
    monkeypatch.setattr(separation, 'TRACKS', tmp_path)
    result = engine.source_clip({'id':'abc', 'name':'test', 'downbeat':0}, 'vocals', start, 1,
        120, 120, 0, threading.Event(), quality='standard', head_seconds=.8, tail_seconds=.8)
    head = round(.8*SR)
    offset = round(start*SR)
    np.testing.assert_array_equal(result[head:head+2*SR], original[offset:offset+2*SR])
    np.testing.assert_array_equal(result[-head:], original[offset+2*SR:offset+2*SR+head])
    if start == 0:
        assert np.max(abs(result[:head])) == 0
    else:
        np.testing.assert_array_equal(result[:head], original[offset-head:offset])


def test_planner_favors_a_pause_bounded_phrase_over_a_cut_word():
    from studio.quality import candidates
    from test_structure import fixture
    profile = fixture()
    profile['vocal_gaps'] = [(15.8, 16.2), (31.8, 32.2)]
    choices = {c['index']:c for c in candidates(profile, 8)}
    assert choices[8]['phrase_risk'] == 0
    assert choices[9]['phrase_risk'] == 1


def test_real_pitch_and_time_processing_keep_pickup_context_off_the_bar_grid(tmp_path, monkeypatch):
    from studio import engine, separation
    from studio.analysis import SR
    folder = tmp_path/'abc'/'stems'; folder.mkdir(parents=True)
    original = np.zeros((6*SR, 2), np.float32)
    size = round(.12*SR)
    tone = .1*np.sin(2*np.pi*440*np.arange(size)/SR)*np.hanning(size)
    for at in (2.3, 3.3):
        pos = round(at*SR)
        original[pos:pos+size] = stereo(tone)
    sf.write(folder/'vocals.wav', original, SR, subtype='FLOAT')
    monkeypatch.setattr(engine, 'TRACKS', tmp_path)
    monkeypatch.setattr(separation, 'TRACKS', tmp_path)
    result = engine.source_clip({'id':'abc', 'name':'test', 'downbeat':0}, 'vocals', 2, 1,
        120, 100, 2, threading.Event(), quality='standard', head_seconds=.8, tail_seconds=.8)
    assert len(result) == 4*SR
    power = np.convolve(result[:, 0]**2, np.ones(441)/441, mode='same')
    for expected in (.8+.36+.072, .8+1.56+.072):
        left, right = round((expected-.15)*SR), round((expected+.15)*SR)
        actual = (left+np.argmax(power[left:right]))/SR
        assert abs(actual-expected) < .05
