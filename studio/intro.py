"""Plan a connected opening and reveal its rhythm before the first vocal."""
import json
import numpy as np
from .storage import TRACKS


def choose_intro(profile, entry):
    """Compare only lead-ins that actually connect to the selected backing."""
    bars = profile['bars']
    following = np.mean([b['energy'] for b in bars[entry:entry+4]])
    choices = []
    for count in (8, 4):
        if entry < count:
            continue
        rows = bars[entry-count:entry]
        if not all(b['regular'] for b in rows):
            continue
        energy = np.array([b['energy'] for b in rows])
        reference = max(float(following), float(np.mean(energy)), 1e-6)
        opening = float(np.mean(energy[:count//2]))/reference
        rise = float(np.mean(energy[count//2:])-np.mean(energy[:count//2]))/reference
        jumps = float(np.max(abs(np.diff(energy))))/reference
        score = .12*(count == 8)-.18*min(opening, 2)+.18*np.clip(rise, -1, 1)-.08*min(jumps, 2)
        choices.append({'bars': count, 'index': entry-count, 'start': rows[0]['start'],
                        'end': bars[entry]['start'], 'score': float(score), 'strategy': 'connected-lead-in'})
    return max(choices, key=lambda c:c['score']) if choices else None


def lead_in(track, start, max_bars=8, manual_bpm=None):
    """Use the preceding bars, or preview the coming motif if none exist."""
    from .engine import clip_timing, local_timing, snap_start
    bpm = manual_bpm or track['bpm']
    path = TRACKS/track['id']/'beat-grid.json' if track.get('id') else None
    if path and path.exists() and not manual_bpm:
        grid = np.asarray(json.loads(path.read_text())['downbeats'])
        index = int(np.argmin(abs(grid-start)))
        for version in (3, 2):
            cached = path.parent/f'musical-profile-v{version}.json'
            if cached.exists():
                profile = json.loads(cached.read_text())
                if index < len(profile['bars']) and abs(profile['bars'][index]['start']-grid[index]) < .03:
                    selected = choose_intro(profile, index)
                    if selected and selected['bars'] <= max_bars:
                        return selected
                break
        median = float(np.median(np.diff(grid)))
        for count in (8, 4):
            if count <= max_bars and index >= count and np.all(abs(np.diff(grid[index-count:index+1])/median-1) < .12):
                return {'start': float(grid[index-count]), 'end': float(grid[index]), 'bars': count, 'strategy': 'connected-lead-in'}
        count = min(4, max_bars, len(grid)-index-1)
        if count < 1:
            raise ValueError('Zu wenig Musik für ein Intro am gewählten Einstieg.')
        return {'start': float(grid[index]), 'end': float(grid[index+count]), 'bars': count, 'strategy': 'motif-preview'}
    if track.get('id'):
        begin, _, _, _ = clip_timing(track, start, 1, bpm, bool(manual_bpm))
        _, bpm = local_timing(track, start, bpm, bool(manual_bpm))
    else:
        begin = snap_start(start, track, bpm)
    for count in (8, 4):
        preceding = begin-count*240/bpm
        if count <= max_bars and preceding >= 0:
            return {'start': preceding, 'end': begin, 'bars': count, 'strategy': 'connected-lead-in'}
    available = int((track['duration']-begin)*bpm/240)
    count = min(4, max_bars, available)
    if count < 1:
        raise ValueError('Zu wenig Musik für ein Intro am gewählten Einstieg.')
    return {'start': begin, 'end': begin+count*240/bpm, 'bars': count, 'strategy': 'motif-preview'}


def rebuild_intro(tracks, sections, bpms=None):
    """Replace only the opening; keep the user's subsequent arrangement intact."""
    remaining = [dict(s) for s in sections]
    while remaining and remaining[0]['effect'] == 'intro':
        remaining.pop(0)
    if not remaining:
        raise ValueError('Nach dem Intro wird mindestens ein Musikabschnitt benötigt.')
    if len(remaining) >= 16:
        raise ValueError('Für das Intro ist ein freier Abschnitt nötig (höchstens 16 insgesamt).')
    first = remaining[0]
    sources = ('A', 'B') if first['instrumental'] == 'hybrid' else (first['instrumental'],)
    bpms = bpms or {}
    leads = {s:lead_in(tracks[s], first['start_'+s.lower()], manual_bpm=bpms.get(s)) for s in sources}
    count = min(v['bars'] for v in leads.values())
    for source in sources:
        if leads[source]['bars'] != count:
            leads[source] = lead_in(tracks[source], first['start_'+source.lower()], count, bpms.get(source))
    intro = {**first, 'name': 'Intro · Motiv aufbauen', 'bars': count, 'vocal': 'none',
             'effect': 'intro', 'vocal_db': 0., 'vocal_offset': 0.}
    for source, lead in leads.items():
        intro['start_'+source.lower()] = round(lead['start'], 3)
    return {'sections': [intro]+remaining, 'intro': {'bars': count, 'sources': leads}}


def rhythm_gain(progress, stem):
    """Keep a quiet pulse; arrive at full bass/drums before the vocal entry."""
    begin, end, floor = (.2, .9, .12) if stem == 'drums' else (.1, .75, .2)
    t = np.clip((np.asarray(progress)-begin)/(end-begin), 0, 1)
    return floor+(1-floor)*(t*t*(3-2*t))


def preview_sections(sections, budget=32):
    result = []
    for section in sections:
        if budget <= 0:
            break
        count = min(section.bars, budget)
        result.append(section.model_copy(update={'bars': count}))
        budget -= count
    return result
