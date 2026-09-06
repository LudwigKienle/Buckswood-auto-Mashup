"""Conservative, energy-based vocal edit handles. No lyric interpretation."""
import numpy as np

HANDLE_SECONDS = 1.6


def handle_duration(bpm):
    # Two beats accommodate common pickups and held releases. The small margin
    # covers detector quantization and the edit pad inside the bounding pause.
    return min(HANDLE_SECONDS, 120/bpm+.08)


def quiet_regions(envelope, times, reference, min_gap=.12):
    """Require a sustained pause; short gaps between consonants are not edits."""
    if len(times) < 2:
        return []
    hop = float(np.median(np.diff(times)))
    quiet = np.asarray(envelope) < max(1e-5, reference*.12)
    edges = np.diff(np.r_[False, quiet, False].astype(int))
    return [(float(times[a]), float(times[b-1]+hop))
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
            if (b-a)*hop >= min_gap-1e-8]


def phrase_boundary(gaps, at, side, limit=HANDLE_SECONDS):
    """Recover a crossing vocal only if a nearby pause bounds the whole handle.

    Clearance describes silence already INSIDE the selected bars; extension is
    actual source audio OUTSIDE them. The bar grid itself must never move.
    """
    for start, end in gaps:
        if start <= at <= end:
            return {'extension': 0., 'clearance': max(0., end-at if side == 'start' else at-start), 'risk': 0.}
    if side == 'start':
        cuts = [max(start, end-.035) for start, end in gaps if end <= at]
        extension = at-max(cuts) if cuts else float('inf')
    elif side == 'end':
        cuts = [min(end, start+.035) for start, end in gaps if start >= at]
        extension = min(cuts)-at if cuts else float('inf')
    else:
        raise ValueError('Unknown vocal boundary side.')
    if 0 < extension <= limit:
        return {'extension': float(extension), 'clearance': 0., 'risk': .2+.3*extension/limit}
    return {'extension': 0., 'clearance': 0., 'risk': 1.}


def audio_regions(audio, sr, reference):
    """10 ms stereo RMS, without cancelling out-of-phase stereo vocals."""
    block = max(1, round(sr*.01))
    n = len(audio)//block
    if n < 2:
        return []
    levels = np.sqrt(np.mean(audio[:n*block].astype(np.float64).reshape(n, block, -1)**2, axis=(1, 2)))
    return quiet_regions(levels, np.arange(n)*block/sr, reference)


def restore_vocal_edges(vocals, parts, heads, tails, continuations, sections, sr, reference, limit=HANDLE_SECONDS):
    """Overlay complete pickups/releases only in vacant vocal timeline space.

    No generated audio, no stretching a word twice, no moving a downbeat. An
    uncertain or occupied handle is skipped, never squeezed between singers.
    """
    edits = []
    positions = np.r_[0, np.cumsum([len(p) for p in parts])]
    margin = round(.25*sr)
    fade = max(1, round(.006*sr))

    def vacant(audio):
        block = max(1, round(.01*sr))
        power = np.mean(audio.astype(np.float64)**2, axis=1)
        if not len(power):
            return False
        padded = np.pad(power, (0, (-len(power)) % block))
        return np.sqrt(padded.reshape(-1, block).mean(axis=1)).max() < max(1e-5, reference*.12)

    # Finish the outgoing word before considering the next singer's pickup.
    for i, part in enumerate(parts):
        if sections[i].vocal == 'none':
            continue
        for side in ('start', 'end'):
            if side == 'start' and continuations[i]:
                continue
            if side == 'end' and i+1 < len(parts) and continuations[i+1]:
                continue
            at = int(positions[i if side == 'start' else i+1])
            handle = heads[i] if side == 'start' else tails[i]
            if sections[i].vocal_offset:
                info = {'extension': 0., 'risk': 0.}
            else:
                context = np.concatenate([handle, part[:margin]]) if side == 'start' else np.concatenate([part[-margin:], handle])
                cut = len(handle)/sr if side == 'start' else min(len(part), margin)/sr
                info = phrase_boundary(audio_regions(context, sr, reference), cut, side, limit)
            n = min(round(info['extension']*sr), len(handle))
            applied = False
            if n:
                left, right = (at-n, at) if side == 'start' else (at, at+n)
                if left >= 0 and right <= len(vocals) and vacant(vocals[left:right]):
                    extension = (handle[-n:] if side == 'start' else handle[:n]).copy()
                    f = min(fade, n)
                    if side == 'start':
                        extension[:f] *= np.linspace(0, 1, f)[:, None]
                    else:
                        extension[-f:] *= np.linspace(1, 0, f)[:, None]
                    vocals[left:right] += extension
                    applied = True
                edits.append({'section': i+1, 'side': side, 'seconds': round(n/sr, 3),
                              'status': 'restored' if applied else 'no-space'})
            elif info['risk'] == 1.:
                # Preserve the previous short release for an unbounded sustain
                # into silence. This is a fade, not a recovered complete word.
                f = min(round(.18*sr), len(handle))
                if side == 'end' and f and at+f <= len(vocals) and vacant(vocals[at:at+f]):
                    vocals[at:at+f] += handle[:f]*np.linspace(1, 0, f)[:, None]
                    applied = True
                    edits.append({'section': i+1, 'side': side, 'seconds': round(f/sr, 3), 'status': 'faded-release'})
                else:
                    edits.append({'section': i+1, 'side': side, 'seconds': 0., 'status': 'no-pause'})
            if not applied:
                # A very short fade prevents a click when a complete handle
                # cannot fit. It deliberately makes no claim to recover a word.
                f = min(fade, len(part))
                if side == 'start':
                    vocals[at:at+f] *= np.linspace(0, 1, f)[:, None]
                else:
                    vocals[at-f:at] *= np.linspace(1, 0, f)[:, None]
    return edits
