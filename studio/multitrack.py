"""Optional guest themes over the established B accompaniment, with an A return.

The pair remains the form's anchor. This is acoustic matching, not lyric semantics.
"""
import numpy as np
from .arrangement_metrics import tempo_fit


def add_themes(result, profiles, check=lambda: None):
    from .quality import candidates, compatibility
    from .phrases import handle_duration
    target = result['analysis']['planning_bpm']
    bed_start = result['sections'][1]['start_b']
    bed_index = int(np.argmin([abs(r['start']-bed_start) for r in profiles['B']['bars']]))
    guest_sections, details = [], {}
    for name in sorted(profiles.keys()-{'A', 'B'}):
        check()
        profile = profiles[name]
        best = None
        for count in (16, 8):
            if count > result['analysis']['phrase_bars']:
                continue
            bed = profiles['B']['bars'][bed_index:bed_index+count]
            harmony = np.concatenate([r['harmony'] for r in bed])
            for candidate in candidates(profile, count, handle_duration(target)*target/profile['bpm']):
                check()
                if not .3 <= candidate['coverage'] <= .98:
                    continue
                rows = profile['bars'][candidate['index']:candidate['index']+count]
                warp = tempo_fit(rows, target)
                for pitch in range(-5, 6):
                    match = compatibility(candidate['voice'], harmony, candidate['active'],
                                          voice_shift=pitch, harmony_shift=result['pitch_b'])
                    value = (match-.18*candidate['vocal_flow']['cost']-.18*candidate['cut']
                             -.16*candidate['phrase_risk']-.12*candidate['internal_change']
                             -.10*warp['cost']-.025*abs(pitch)+.025*(count == 16))
                    if best is None or value > best[0]:
                        best = value, candidate, pitch, count, warp, match
        if best is None:
            raise ValueError(f'Track {name}: keine passende zusammenhängende Gesangspassage. Bitte einfachen Plan verwenden oder einen anderen Song wählen.')
        _, candidate, pitch, count, warp, match = best
        # A short instrumental lead-in clears the preceding lyric and reintroduces
        # the familiar backing before the guest. Do not alternate singers per bar.
        lead = profiles['B']['bars'][bed_index-4]['start']
        common = {'start_a': result['sections'][1]['start_a'], 'start_b': round(bed_start, 3),
                  'start_'+name.lower(): candidate['start'], 'instrumental': 'B',
                  'effect': 'normal', 'vocal_db': 0, 'instrumental_db': -1, 'vocal_offset': 0}
        guest_sections += [{**common, 'name': f'Übergang zu {name}', 'vocal': 'none', 'bars': 4, 'start_b': round(lead, 3)},
                           {**common, 'name': f'Thema {name} · ganze Passage', 'vocal': name, 'bars': count}]
        result['pitch_'+name.lower()] = pitch
        details[name] = {'bars': count, 'start': candidate['start'], 'end': candidate['end'],
                         'pitch': pitch, 'similarity': match, 'tempo_fit': warp}
    # Preserve intro, complete B response, build, A reprise and outro.
    result['sections'][4:4] = guest_sections
    duration = sum(s['bars'] for s in result['sections'])*240/target
    result['analysis'].update(version=9, extra_themes=details, duration_seconds=round(duration, 2))
    result['analysis']['note'] = (f'Geplant sind {len(profiles)} Songs und etwa {round(duration)//60}:{round(duration)%60:02d} Minuten. '
        'A und B bilden die Grundstruktur. Weitere Songs bekommen jeweils eine ganze Gesangspassage über der vertrauten Begleitung von B, '
        'mit vier instrumentalen Takten davor. Thema A kehrt zum Schluss zurück. '
        'Tonhöhe, Gesangspausen und lokale Tempoänderungen werden verglichen; Textbedeutung wird nicht verstanden.')
    return result


def simple_plan(tracks):
    from .analysis import auto_plan
    sections = auto_plan(tracks['A'], tracks['B'])
    insert = next((i for i, s in enumerate(sections) if s['effect'] == 'outro'), len(sections))
    for name in sorted(tracks.keys()-{'A', 'B'}):
        template = next(s for s in auto_plan(tracks[name], tracks['B']) if s['vocal'] == 'A')
        sections.insert(insert, {**template, 'name': f'Thema {name} · Einstieg prüfen',
            'vocal': name, 'instrumental': 'B', 'effect': 'normal',
            'start_'+name.lower(): template['start_a'], 'start_a': 0})
        insert += 1
    return sections
