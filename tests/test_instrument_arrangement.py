import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError
from studio.engine import backing_components, backing_runs
from studio.instrument_arrangement import suggest_instruments, available_backends, validate_routes
from studio.models import RenderRequest, Section
from studio import instrument_arrangement as arranger
from studio import lalal, separation


def test_individual_sources_are_validated_and_routed():
    section = Section(name='Drop', vocal='A', instrumental='B', instrument_sources={
        'drums': 'B', 'bass': 'A', 'piano': 'A', 'strings': 'off'},
        instrument_levels_db={'piano': -12})
    assert backing_components(section) == (('B', 'drums'), ('A', 'bass'), ('A', 'piano'))
    assert backing_components(Section(name='Core',instrument_sources={'drums':'B','bass':'B','other':'B','piano':'A'})) == (('B','instrumental'),('A','piano'))
    assert backing_components(Section(name='Hybrid',instrument_sources={'drums':'B','bass':'A','other':'A'})) == (('B','drums'),('A','harmony'))
    sections = [section, section.model_copy(update={'name': 'Drop 2', 'start_a': 16, 'start_b': 16})]
    runs = backing_runs(sections, lambda s, source: (getattr(s, 'start_'+source.lower()), getattr(s, 'start_'+source.lower())+16))
    assert runs[1, 'A', 'piano'] == (0, 16, 8)
    request = dict(track_a='a', track_b='b', sections=[section.model_dump()])
    assert RenderRequest(**request, separation_quality='lalal_full').sections[0].instrument_levels_db['piano'] == -12
    assert RenderRequest(**request, separation_quality='lalal_mixed').sections[0].instrument_sources['piano'] == 'A'
    validate_routes([section], {'A':'lalal_full','B':'hq'})
    with pytest.raises(ValueError, match='Track A'):
        validate_routes([section], {'A':'hq','B':'lalal_full'})
    with pytest.raises(ValidationError, match='Einzelinstrumente'):
        RenderRequest(**request)
    with pytest.raises(ValidationError, match='Spur muss ein Song'):
        RenderRequest(**{**request, 'sections': [{**section.model_dump(), 'instrument_sources': {'piano': 'C'}}]}, separation_quality='lalal_full')
    with pytest.raises(ValidationError, match='Instrumentenpegel'):
        Section(name='Bad', instrument_sources={'piano': 'A'}, instrument_levels_db={'piano': 12})


def test_automatic_plan_uses_only_cached_stems_and_avoids_same_source_doubling(tmp_path, monkeypatch):
    monkeypatch.setattr(arranger, 'TRACKS', tmp_path)
    monkeypatch.setattr(arranger, 'FULL_FOLDER', 'full')
    rate = 44100
    for id in ('a', 'b'):
        folder = tmp_path/id/'full';folder.mkdir(parents=True)
        samples = np.full((rate*4, 2), .2, np.float32)
        sf.write(folder/'instrumental.wav', samples, rate, subtype='FLOAT')
        sf.write(folder/'vocals.wav', np.zeros_like(samples), rate, subtype='FLOAT')
        for name in arranger.MELODIC:
            sf.write(folder/f'{name}.wav', samples*(.4 if name=='piano' else .01), rate, subtype='FLOAT')
    sections = [{'name':'Intro','instrumental':'B','vocal':'none','effect':'intro','start_a':0,'start_b':0},
                {'name':'Theme','instrumental':'B','vocal':'A','effect':'normal','start_a':0,'start_b':0},
                {'name':'Drop','instrumental':'hybrid','vocal':'A','effect':'drop','start_a':0,'start_b':0}]
    suggest_instruments(sections, {'A':{'id':'a'},'B':{'id':'b'}}, {'A':'lalal_full','B':'lalal_full'})
    assert sections[0]['instrument_sources'] == {'drums':'B','bass':'B','other':'B'}
    assert sections[1]['instrument_sources']['piano'] == 'A'
    assert sections[1]['instrument_levels_db']['piano'] == -16
    assert sections[2]['instrument_sources']['piano'] == 'B'
    assert sections[2]['instrument_sources']['other'] == 'A'


def test_mixed_plan_only_uses_full_stems_for_melodic_accents(tmp_path, monkeypatch):
    monkeypatch.setattr(arranger, 'TRACKS', tmp_path)
    monkeypatch.setattr(arranger, 'FULL_FOLDER', 'full')
    folder=tmp_path/'a'/'full';folder.mkdir(parents=True)
    audio=np.full((44100*4, 2), .2, np.float32)
    sf.write(folder/'instrumental.wav', audio, 44100, subtype='FLOAT')
    sf.write(folder/'vocals.wav', np.zeros_like(audio), 44100, subtype='FLOAT')
    for stem in arranger.MELODIC:
        sf.write(folder/f'{stem}.wav', audio*(.4 if stem=='synthesizer' else .01), 44100, subtype='FLOAT')
    tracks={'A':{'id':'a'},'B':{'id':'b'}}
    sections=[{'name':'A over B','instrumental':'B','vocal':'A','effect':'normal','start_a':0,'start_b':0},
              {'name':'B over A','instrumental':'A','vocal':'B','effect':'normal','start_a':0,'start_b':0}]
    suggest_instruments(sections, tracks, {'A':'lalal_full','B':'hq'})
    assert sections[0]['instrument_sources']['synthesizer']=='A'
    assert sections[1]['instrument_sources']=={'drums':'A','bass':'A','other':'A'}
    monkeypatch.setattr('studio.separation.selected_backend', lambda track,quality:'hq')
    with pytest.raises(ValueError, match='mindestens'):
        available_backends(tracks,'lalal_mixed')


def test_mixed_backend_uses_existing_local_stems_without_paid_calls(monkeypatch):
    monkeypatch.setattr(lalal, 'ready', lambda track,mode='vocals': track['id']=='a' and mode=='all')
    monkeypatch.setattr(separation, 'ready', lambda track: track['id']=='b')
    tracks={'A':{'id':'a'},'B':{'id':'b'},'C':{'id':'c'}}
    assert available_backends(tracks,'lalal_mixed') == {'A':'lalal_full','B':'hq','C':'standard'}
    assert separation.selected_backend(tracks['B'],'lalal_mixed')=='hq'


def test_mixed_backend_reuses_cached_lalal_vocals_before_local_stems(monkeypatch):
    monkeypatch.setattr(lalal, 'ready', lambda track,mode='vocals':
                        (track['id']=='a' and mode=='all') or (track['id']=='b' and mode=='vocals'))
    monkeypatch.setattr(separation, 'ready', lambda track: True)
    assert available_backends({'A':{'id':'a'},'B':{'id':'b'}},'lalal_mixed') == {
        'A':'lalal_full','B':'lalal'}


def test_mixed_api_plans_cached_accent_and_rejects_missing_stem(monkeypatch):
    from fastapi.testclient import TestClient
    from studio import server
    monkeypatch.setattr(server,'read_track',lambda id:{'id':id,'name':id})
    monkeypatch.setattr(arranger,'available_backends',lambda tracks,quality:{'A':'lalal_full','B':'hq'})
    monkeypatch.setattr(arranger,'_accent',lambda track,start:'synthesizer')
    client=TestClient(server.app)
    headers={'x-studio-token':server.token}
    request={'track_a':'a','track_b':'b','separation_quality':'lalal_mixed',
             'sections':[{'name':'Theme','bars':8,'vocal':'A','instrumental':'B','effect':'normal'}]}
    planned=client.post('/api/instrument-plan',json=request,headers=headers)
    assert planned.status_code==200
    assert planned.json()['sections'][0]['instrument_sources']['synthesizer']=='A'
    invalid={**request,'sections':[{**request['sections'][0],
             'instrument_sources':{'drums':'B','other':'B','piano':'B'}}]}
    rejected=client.post('/api/render',json=invalid,headers=headers)
    assert rejected.status_code==400 and 'Track B' in rejected.json()['detail']
