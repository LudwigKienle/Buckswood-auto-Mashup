import numpy as np
from studio.quality import add_structure, coherent_plan, compatibility


def fixture(change=False):
    return {'bpm':120, 'voice_reference':1, 'bars':[
        {'start':i*2., 'end':(i+1)*2., 'regular':True, 'cut':.05, 'end_cut':.05,
         'voice':np.eye(12)[[0,4,7,0,4,7,0,4]].tolist(),
         'harmony':np.eye(12)[[0,4,7,0,4,7,0,4]].tolist(),
         'activity':[1,1,1,1,0,0,0,0], 'energy':.1,
         'structure':1. if change and i%8==0 else 0.} for i in range(64)]}


def test_shorter_themes_avoid_crossing_strong_structure_change():
    result = coherent_plan({'A':fixture(True), 'B':fixture(True)}, fixed_pitch=0)
    assert result['analysis']['phrase_bars'] == 8
    assert result['analysis']['internal_structure_change'] == {'A':0., 'B':0.}
    stable = coherent_plan({'A':fixture(), 'B':fixture()}, fixed_pitch=0)
    assert stable['analysis']['phrase_bars'] == 16


def test_sustained_timbre_change_is_found_without_marking_every_bar():
    rows = [{'texture':[0.]*8 if i<16 else [40.]*8, 'activity':[1.]*8} for i in range(32)]
    add_structure(rows, 1.)
    assert rows[16]['structure'] >= .3
    assert sum(row['structure'] > 0 for row in rows) <= 3


def test_harmony_score_penalizes_a_bad_subphrase_despite_good_average():
    voice = np.tile(np.eye(12)[0], (16, 1))
    harmonic = voice.copy(); harmonic[6:10] = np.eye(12)[1]
    result = compatibility(voice, harmonic, np.ones(16, dtype=bool))
    assert result < .7
