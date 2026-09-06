"""Thin wrapper around Rubber Band's public C API (4.0.0).

The pylibrb 0.1.2 wheel cannot convert Python dictionaries for its keyframe
method. The public C API accepts parallel arrays and avoids that binding bug.
"""
import ctypes as ct
from enum import IntFlag
import numpy as np
from .storage import DATA

_library = None


class Option(IntFlag):
    """Values from Rubber Band 4.0.0's public rubberband-c.h interface.

    Copyright 2007-2024 Particular Programs Ltd; GPL-2.0-or-later.
    See THIRD_PARTY_NOTICES.md. No additional Python binding is required.
    """
    PROCESS_OFFLINE = 0x00000000
    ENGINE_FASTER = 0x00000000
    ENGINE_FINER = 0x20000000
    CHANNELS_TOGETHER = 0x10000000
    THREADING_NEVER = 0x00010000
    FORMANT_PRESERVED = 0x01000000


def library():
    global _library
    if _library is not None:
        return _library
    path = DATA / 'rubberband-build/librubberband.dylib'
    if not path.exists():
        raise RuntimeError('Die native Audio-Bibliothek fehlt. Bitte scripts/setup.sh ausführen.')
    lib = ct.CDLL(str(path))
    state, uint, fp = ct.c_void_p, ct.c_uint, ct.POINTER(ct.c_float)
    signatures = {
        'new': ([uint, uint, ct.c_int, ct.c_double, ct.c_double], state),
        'delete': ([state], None),
        'set_expected_input_duration': ([state, uint], None),
        'set_max_process_size': ([state, uint], None),
        'set_key_frame_map': ([state, uint, ct.POINTER(uint), ct.POINTER(uint)], None),
        'study': ([state, ct.POINTER(fp), uint, ct.c_int], None),
        'process': ([state, ct.POINTER(fp), uint, ct.c_int], None),
        'available': ([state], ct.c_int),
        'retrieve': ([state, ct.POINTER(fp), uint], uint),
    }
    for name, (args, restype) in signatures.items():
        function = getattr(lib, 'rubberband_'+name)
        function.argtypes, function.restype = args, restype
    _library = lib
    return lib


def pointers(audio):
    fp = ct.POINTER(ct.c_float)
    return (fp*len(audio))(*(channel.ctypes.data_as(fp) for channel in audio))


def offline(audio, sample_rate, options, ratio, pitch_scale, keyframes=None):
    lib = library()
    data = np.ascontiguousarray(audio.T, dtype=np.float32)
    state = lib.rubberband_new(sample_rate, len(data), options, ratio, pitch_scale)
    if not state:
        raise RuntimeError('Rubber Band konnte nicht initialisiert werden.')
    try:
        lib.rubberband_set_expected_input_duration(state, data.shape[1])
        lib.rubberband_set_max_process_size(state, 8192)
        if keyframes:
            pairs = sorted((int(x), int(y)) for x,y in keyframes.items() if x > 0)
            if any(a < 0 or b < 0 for a,b in pairs) or any(y[1] <= x[1] for x,y in zip(pairs,pairs[1:])):
                raise ValueError('Zeitmarken müssen positiv und streng aufsteigend sein.')
            n = len(pairs)
            lib.rubberband_set_key_frame_map(state, n, (ct.c_uint*n)(*(x for x,y in pairs)),
                                             (ct.c_uint*n)(*(y for x,y in pairs)))
        output = []
        for stage in ('study', 'process'):
            call = getattr(lib, 'rubberband_'+stage)
            for start in range(0, data.shape[1], 8192):
                block = np.ascontiguousarray(data[:, start:start+8192])
                call(state, pointers(block), block.shape[1], start+8192 >= data.shape[1])
                if stage == 'process':
                    available = lib.rubberband_available(state)
                    if available > 0:
                        buffer = np.empty((len(data), available), np.float32)
                        actual = lib.rubberband_retrieve(state, pointers(buffer), available)
                        output.append(buffer[:, :actual])
        if not output:
            raise RuntimeError('Rubber Band hat keine Audiodaten erzeugt.')
        return np.concatenate(output, axis=1).T.copy()
    finally:
        lib.rubberband_delete(state)
