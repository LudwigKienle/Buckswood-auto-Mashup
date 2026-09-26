"""Conservative, editable instrument routing for cached LALAL.AI stems.

The provider's individual melodic estimates are not additive: ``other`` is
the direct instrumental less drums and bass, so it still contains melodies.
Keep that residual as the familiar bed and add at most one quiet motif from a
different song. The editor can replace this suggestion instrument by instrument.
"""
from pathlib import Path
import numpy as np
import soundfile as sf
from .storage import TRACKS
from .lalal import FULL_FOLDER

MELODIC = ('piano', 'electric_guitar', 'acoustic_guitar', 'synthesizer', 'strings', 'wind')


def available_backends(tracks, quality):
    """Select local fallbacks without starting a paid or local separation job."""
    from .separation import selected_backend
    backends = {name: selected_backend(track, quality) for name, track in tracks.items()}
    if quality == 'lalal_mixed' and 'lalal_full' not in backends.values():
        raise ValueError('Für den Mischmodus benötigt mindestens ein Song bereits alle LALAL.AI-Instrumente.')
    return backends


def validate_routes(sections, backends):
    from .engine import backing_components
    for section in sections:
        for source, stem in backing_components(section):
            if stem in MELODIC and backends[source] != 'lalal_full':
                raise ValueError(f'Track {source}: {stem} benötigt vollständig getrennte LALAL.AI-Instrumente.')


def _sample(path: Path, start: float, seconds=3.):
    with sf.SoundFile(path) as audio:
        audio.seek(min(max(0, round(start*audio.samplerate)), len(audio)))
        return audio.read(round(seconds*audio.samplerate), dtype='float32', always_2d=True)


def _accent(track, start):
    folder = TRACKS/track['id']/FULL_FOLDER
    reference = _sample(folder/'instrumental.wav', start)
    if not len(reference):
        return None
    level = float(np.sqrt(np.mean(reference**2)))
    if level < .002:
        return None
    voice = _sample(folder/'vocals.wav', start)
    voice_level = float(np.sqrt(np.mean(voice**2))) if len(voice) else 0.
    best = None
    for stem in MELODIC:
        audio = _sample(folder/f'{stem}.wav', start)
        n = min(len(audio), len(voice))
        if not len(audio):
            continue
        rms = float(np.sqrt(np.mean(audio**2)))
        relative = rms/level
        if not .07 <= relative <= 1.4:
            continue
        # An apparent "instrument" which tracks the singer is likely bleed.
        similarity = abs(float(np.mean(audio[:n]*voice[:n])))/(rms*voice_level+1e-9) if n and voice_level>.002 else 0.
        if similarity > .35:
            continue
        score = min(relative, .65)-.3*similarity
        if best is None or score > best[0]:
            best = (score, stem)
    return best[1] if best else None


def suggest_instruments(sections, tracks, backends=None):
    """Route the core bed separately and add a low-level cross-song motif.

    No remote calls or paid processing happen here. Every stem is already cached.
    """
    if backends is None:
        backends = available_backends(tracks, 'lalal_full')
    for section in sections:
        main = section['instrumental']
        if main == 'hybrid':
            routing = {'drums': 'B', 'bass': 'A', 'other': 'A'}
            bed = 'A'
        else:
            routing = {'drums': main, 'bass': main, 'other': main}
            bed = main
        levels = {}
        # A single, quiet different-song motif gives the separate instruments a
        # purpose without doubling the residual from their own original song.
        if section['effect'] in ('normal', 'build', 'drop'):
            accent_source = section['vocal'] if section['vocal'] not in ('none', bed) else ('A' if bed != 'A' else 'B')
            if accent_source in tracks and accent_source != bed and backends[accent_source] == 'lalal_full':
                stem = _accent(tracks[accent_source], section.get('start_'+accent_source.lower(), 0))
                if stem:
                    routing[stem] = accent_source
                    levels[stem] = -12 if section['effect'] == 'drop' else -16
        section['instrument_sources'] = routing
        section['instrument_levels_db'] = levels
    return sections
