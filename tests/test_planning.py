from studio.analysis import auto_plan

def test_plan_prioritizes_audible_vocals_over_tempo_similarity():
    track={'bpm':123,'duration':270,'downbeat':0,'candidates':[
        {'start':48,'bpm':92,'energy':.15,'vocal_energy':.12},
        {'start':72,'bpm':92,'energy':.16,'vocal_energy':.11},
        {'start':208,'bpm':125,'energy':.02,'vocal_energy':.0002},
        {'start':217,'bpm':125,'energy':.02,'vocal_energy':.0002}]}
    plan=auto_plan(track,track)
    for section in plan:
        if section['vocal']=='A': assert section['start_a']<200
        if section['vocal']=='B': assert section['start_b']<200
