import numpy as np
import soundfile as sf
import pytest
from studio.analysis import SR
from studio.engine import (read_component, backing_runs, join_parts, mix_space,
                           duck_envelope, timing_map, source_clip)
from studio.models import Section


def test_shared_stem_leakage_cancels_before_warp(tmp_path):
    t = np.arange(SR)/SR
    leakage = .08*np.sin(2*np.pi*440*t)
    bass = .1*np.sin(2*np.pi*80*t)
    channels = lambda x: np.repeat(x[:, None], 2, axis=1).astype('float32')
    sf.write(tmp_path/'bass.wav', channels(bass+leakage), SR, subtype='FLOAT')
    sf.write(tmp_path/'other.wav', channels(-leakage), SR, subtype='FLOAT')
    combined = read_component(tmp_path, 'harmony', 0, SR)
    np.testing.assert_allclose(combined, channels(bass), atol=2e-8)


def test_existing_hq_instrumental_is_used_without_rebuilding_it(tmp_path):
    wave = np.random.default_rng(12).normal(0, .05, (SR, 2)).astype('float32')
    sf.write(tmp_path/'instrumental.wav', wave, SR, subtype='FLOAT')
    np.testing.assert_array_equal(read_component(tmp_path, 'instrumental', 123, 1000), wave[123:1123])


def test_backing_survives_singer_switch_but_not_source_jump():
    sections = [Section(name='1', vocal='A', instrumental='B', start_b=10, bars=8),
                Section(name='2', vocal='B', instrumental='B', start_b=26, bars=8),
                Section(name='3', instrumental='B', start_b=70, bars=8)]
    runs = backing_runs(sections, lambda s, source: (s.start_b, s.start_b+s.bars*2))
    assert runs[0, 'B', 'instrumental'] == (0, 16, 0)
    assert runs[1, 'B', 'instrumental'] == (0, 16, 8)
    assert runs[2, 'B', 'instrumental'] == (2, 8, 0)


def test_continuous_joins_do_not_modify_samples_even_with_different_tails():
    source = np.random.default_rng(7).normal(0, .04, (SR*2, 2)).astype('float32')
    tail = np.ones((round(.18*SR), 2), np.float32)*.7
    sections = [Section(name='1'), Section(name='2')]
    voice, bed = join_parts([source[:SR].copy(), source[SR:].copy()],
        [source[:SR].copy(), source[SR:].copy()], [(tail, tail), (tail, tail)], sections,
        [False, True], [False, True])
    for signal in (voice, bed):
        np.testing.assert_array_equal(signal[SR-1000:SR+1000], source[SR-1000:SR+1000])


def test_midrange_duck_preserves_bass_stereo_and_unvoiced_bed():
    t = np.arange(3*SR)/SR
    bass, middle = np.sin(2*np.pi*60*t), np.sin(2*np.pi*1000*t)
    bed = np.stack([.07*bass+.05*middle, .035*bass+.025*middle], axis=1).astype('float32')
    vocal = np.repeat((.2*np.sin(2*np.pi*400*t))[:, None], 2, axis=1).astype('float32')
    _, untouched = mix_space(np.zeros_like(vocal), bed.copy(), vocal_gain=1.)
    np.testing.assert_array_equal(untouched, bed)
    _, ducked = mix_space(vocal, bed.copy(), vocal_gain=1.)
    segment = slice(SR, 2*SR)
    amplitude = lambda x, ref: 2*np.mean(x[segment, 0]*ref[segment])
    assert amplitude(ducked, bass) == pytest.approx(amplitude(bed, bass), rel=.002)
    assert .75 < amplitude(ducked, middle)/amplitude(bed, middle) < .9
    np.testing.assert_allclose(ducked[:, 1], ducked[:, 0]*.5, atol=1e-7)


def test_duck_release_bridges_short_gaps_without_holding_forever():
    x = np.zeros((SR*2, 2), np.float32)
    x[:SR] = .1
    env = duck_envelope(x)
    assert env[SR+round(.05*SR)] > .065
    assert env[SR+round(.6*SR)] < .005
    assert np.max(abs(np.diff(env))) < .002


def test_detector_jitter_does_not_force_warp_but_real_drift_does():
    assert timing_map(np.array([0, 2.01, 3.99, 6]), 1., 0, 0, 120) is None
    mapping = timing_map(np.array([0, 2.1, 3.9, 6]), 1., 120, 120, 120)
    assert mapping[120+round(2.1*SR)] == 120+2*SR


def test_source_context_does_not_shift_identity_audio(tmp_path, monkeypatch):
    import studio.engine as engine
    import studio.separation as sep
    folder = tmp_path/'abc'/'stems'; folder.mkdir(parents=True)
    t = np.arange(SR*6)/SR
    wave = np.repeat((.1*np.sin(2*np.pi*220*t))[:, None], 2, axis=1).astype('float32')
    sf.write(folder/'vocals.wav', wave, SR, subtype='FLOAT')
    monkeypatch.setattr(engine, 'TRACKS', tmp_path)
    monkeypatch.setattr(sep, 'TRACKS', tmp_path)
    import threading
    result = source_clip({'id':'abc', 'name':'test', 'downbeat':0}, 'vocals',
                         2, 1, 120, 120, 0, threading.Event(), quality='standard')
    np.testing.assert_array_equal(result, wave[2*SR:4*SR])


def test_import_retains_audio_below_16_bit_quantization(tmp_path, monkeypatch):
    from studio import analysis
    tracks = tmp_path/'tracks'; tracks.mkdir()
    monkeypatch.setattr(analysis, 'TRACKS', tracks)
    monkeypatch.setattr(analysis, 'analyze_track', lambda track_id, name, progress: track_id)
    t = np.arange(SR*10)/SR
    wave = np.repeat((1e-6*np.sin(2*np.pi*400*t))[:, None], 2, axis=1).astype('float32')
    source = tmp_path/'source.wav'
    sf.write(source, wave, SR, subtype='FLOAT')
    track_id = analysis.import_track(source)
    result, rate = sf.read(tracks/track_id/'audio.wav', dtype='float32', always_2d=True)
    assert rate == SR
    assert sf.info(tracks/track_id/'audio.wav').subtype == 'FLOAT'
    np.testing.assert_array_equal(result, wave)
