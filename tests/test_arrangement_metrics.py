import copy
import numpy as np
import pytest
from studio.arrangement_metrics import vocal_flow, tempo_fit, harmonic_jump, regular_bars
from studio.quality import coherent_plan
from test_duration import stable_profile


def test_equal_vocal_coverage_does_not_hide_a_late_entry_and_long_dead_air():
    continuous = np.tile([1, 1, 1, 1, 0, 0, 0, 0], 16)
    scattered = np.r_[np.zeros(32), np.ones(32), np.zeros(32), np.ones(32)]
    assert continuous.mean() == scattered.mean()
    assert vocal_flow(continuous)['cost'] == 0
    assert vocal_flow(scattered)['cost'] > .7
    assert vocal_flow(np.zeros(32))['cost'] == 1


def test_bounded_release_silence_is_not_mistaken_for_internal_dead_air():
    assert vocal_flow([1]*16+[0]*48)['gap_bars'] == 0
    assert vocal_flow([1]*16+[0]*48)['cost'] == 0


def test_tempo_cost_uses_local_bars_and_is_symmetric_in_log_speed():
    rows = [{'start': i*2, 'end': i*2+2} for i in range(8)]
    assert tempo_fit(rows, 120)['cost'] == 0
    assert tempo_fit(rows, 123)['cost'] == 0
    assert tempo_fit(rows, 150)['cost'] == pytest.approx(tempo_fit(rows, 96)['cost'])
    assert tempo_fit(rows, 90)['cost'] > tempo_fit(rows, 110)['cost']
    # Same mean bar duration, but a less uniform performance needs more warping.
    uneven = [{'start':0, 'end':v} for v in [1.7, 2.3]*4]
    assert tempo_fit(uneven, 120)['cost'] > tempo_fit(rows, 120)['cost']


def test_unknown_harmony_is_not_a_clash_and_shift_is_applied_to_outgoing_b():
    c, d = np.eye(12)[0], np.eye(12)[2]
    assert harmonic_jump(c, d) == 1
    assert harmonic_jump(c, d, 2) == 0
    assert harmonic_jump(np.zeros(12), d) == 0


def test_backing_handover_moves_to_better_harmony_without_cutting_vocal_run(monkeypatch):
    from studio import quality
    profiles = {'A':stable_profile(64), 'B':stable_profile(64)}
    # Use independent bar dicts/arrays and equal C harmony everywhere.
    profiles = copy.deepcopy(profiles)
    for p in profiles.values():
        for bar in p['bars']:
            bar['harmony'] = np.tile(np.eye(12)[0], (8, 1)).tolist()
            bar['voice'] = np.tile(np.eye(12)[0], (8, 1)).tolist()
    original = quality.candidates
    def selected(p, count, *args):
        if count != 24:
            return []
        wanted = {0} if p is profiles['A'] else {8, 32}
        return [v for v in original(p, count, *args) if v['index'] in wanted]
    monkeypatch.setattr(quality, 'candidates', selected)
    stable = coherent_plan(profiles, fixed_pitch=0)
    assert stable['analysis']['backing_handover_bars'] == 8
    profiles['B']['bars'][39]['harmony'] = np.tile(np.eye(12)[1], (8, 1)).tolist()
    moved = coherent_plan(profiles, fixed_pitch=0)
    assert moved['analysis']['backing_handover_bars'] == 16
    entry, continuation = moved['sections'][2:4]
    assert entry['vocal'] == continuation['vocal'] == 'B'
    assert continuation['start_b'] == entry['start_b']+entry['bars']*2
    assert entry['bars']+continuation['bars'] == 24
    assert moved['analysis']['backing_harmonic_jump'] == 0


def test_intro_considers_harmonic_instruments_even_when_drums_are_silent():
    from studio.intro import choose_intro
    levels = [1.]*8+[1.2, 1.2, 1.1, .9, .2, .3, .5, .7]+[1.]*4
    bars = [{'start':i*2, 'end':(i+1)*2, 'energy':0., 'backing_energy':v,
             'regular':True} for i, v in enumerate(levels)]
    assert choose_intro({'bars':bars}, 16)['bars'] == 4


def test_local_tempo_region_remains_usable_despite_different_global_tempo():
    spans = np.r_[np.full(40, 2.), np.full(24, 3.2)]
    downbeats = np.r_[0, np.cumsum(spans)]
    beats = np.concatenate([np.linspace(a, b, 4, endpoint=False) for a, b in zip(downbeats[:-1], downbeats[1:])])
    regular = regular_bars(downbeats, beats)
    assert all(regular)
    assert not any(abs(spans[40:]/np.median(spans)-1) < .12)  # Old global test rejected the whole region.


def test_missing_downbeat_and_non_four_beat_regions_are_not_silently_accepted():
    spans = np.r_[np.full(12, 2.), 4., np.full(12, 2.)]
    downbeats = np.r_[0, np.cumsum(spans)]
    beats = np.arange(0, downbeats[-1], .5)
    regular = regular_bars(downbeats, beats)
    assert not regular[12]
    assert sum(regular) == 24
    assert not any(regular_bars(np.arange(0, 32, 2), np.arange(0, 32, 1)))


def test_locally_steady_vocal_region_can_produce_a_compact_plan():
    a, b = stable_profile(64), stable_profile(80)
    spans = np.r_[np.full(40, 2.), np.full(24, 3.2)]
    downbeats = np.r_[0, np.cumsum(spans)]
    valid = regular_bars(downbeats)
    for i, bar in enumerate(a['bars']):
        bar.update(start=float(downbeats[i]), end=float(downbeats[i+1]), regular=valid[i],
                   activity=[0.]*8 if i < 40 else [1.]*4+[0.]*4)
    result = coherent_plan({'A':a, 'B':b}, fixed_pitch=0, target_bpm=100)
    assert result['sections'][1]['start_a'] >= 80
    assert result['analysis']['phrase_bars'] in (8, 16)
