"""Soft arrangement preferences, not universal rules or calibrated quality scores.

See docs/mashup-composition-research.md for evidence and limitations.
"""
import math
import numpy as np


def regular_bars(downbeats, beats=None):
    """Validate local 4/4 runs instead of comparing every bar to one song tempo.

    Do not repair, delete or invent neural beats. Missing/double bar detections
    remain excluded; a sustained tempo change may form a new usable passage.
    """
    downbeats = np.asarray(downbeats, dtype=float)
    spans = np.diff(downbeats)
    beats = np.asarray(beats, dtype=float) if beats is not None else None
    result = []
    for i, span in enumerate(spans):
        local = float(np.median(spans[max(0, i-4):i+5]))
        consistent = span > 0 and local > 0 and abs(span/local-1) < .12
        if beats is not None:
            count = np.searchsorted(beats, downbeats[i+1]-.02)-np.searchsorted(beats, downbeats[i]-.02)
            consistent = consistent and count == 4
        result.append(bool(consistent))
    return result


def vocal_flow(active):
    """Distinguish a continuous response from equal activity in scattered blocks."""
    active = np.asarray(active, dtype=bool)
    voiced = np.flatnonzero(active)
    if not len(voiced):
        return {'entry_bars': len(active)/8, 'gap_bars': len(active)/8, 'cost': 1.}
    # Only internal silence counts: a completed phrase may end before its bar.
    longest = run = 0
    for value in active[voiced[0]:voiced[-1]+1]:
        run = 0 if value else run+1
        longest = max(longest, run)
    entry, gap = voiced[0]/8, longest/8
    cost = .5*min(max(0., entry-.5)/2, 1.) + .5*min(max(0., gap-2)/4, 1.)
    return {'entry_bars': float(entry), 'gap_bars': float(gap), 'cost': cost}


def tempo_fit(rows, target):
    """Measure actual local bar deformation; equal track averages can hide it."""
    local = 240/np.asarray([r['end']-r['start'] for r in rows])
    changes = np.log(target/local)
    # A reciprocal speed change has the same cost. Thresholds are heuristics.
    excess = np.maximum(abs(changes)-math.log(1.08), 0.)/math.log(1.25)
    cost = .7*float(np.mean(excess**2))+.3*float(np.quantile(excess**2, .9))
    return {'cost': cost, 'min_percent': float(np.min((target/local-1)*100)),
            'max_percent': float(np.max((target/local-1)*100))}


def handover_options(count):
    return list(range(8, count, 8)) if count >= 16 else [4]


def transition_context(rows, at, outgoing=False):
    """Two-beat harmonic context; no claim of individual voice-leading analysis."""
    row = rows[at-1 if outgoing else at]
    vector = np.mean(np.asarray(row['harmony'])[-4:] if outgoing else np.asarray(row['harmony'])[:4], axis=0)
    norm = np.linalg.norm(vector)
    return vector/max(norm, 1e-8)


def harmonic_jump(before, after, before_shift=0):
    if np.linalg.norm(before) < 1e-6 or np.linalg.norm(after) < 1e-6:
        return 0.  # Missing evidence must not look like a harmonic clash.
    return float(np.clip(1-np.dot(np.roll(before, before_shift), after), 0, 1))


def backing_change(rows):
    return max((r.get('backing_structure', 0.) for r in rows[1:]), default=0.)
