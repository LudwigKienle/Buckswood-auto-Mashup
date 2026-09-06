"""Isolated Apple GPU worker. No uploads, resampling, clipping or random weights."""
import argparse
import dataclasses
import json
import site
import sys
import time
from pathlib import Path
import numpy as np
import soundfile as sf


def overlap_separate(audio, predict, chunk, hop, progress=lambda *_: None):
    if not 0 < hop <= chunk // 2 or len(audio) < 2:
        raise ValueError('Invalid overlap or empty audio')
    # Reflect context at both edges; normalised Hann overlap retains every sample.
    padded = np.pad(audio, ((chunk, chunk), (0, 0)), mode='reflect')
    starts = list(range(0, len(padded)-chunk+1, hop))
    if starts[-1] != len(padded)-chunk:
        starts.append(len(padded)-chunk)
    window = np.hanning(chunk).astype(np.float32)[:, None]
    output = np.zeros_like(padded, dtype=np.float32)
    weight = np.zeros((len(padded), 1), np.float32)
    for i, start in enumerate(starts):
        estimate = predict(padded[start:start+chunk])
        if estimate.shape != (chunk, 2) or not np.isfinite(estimate).all():
            raise ValueError('Invalid model output; previous stems retained')
        output[start:start+chunk] += estimate * window
        weight[start:start+chunk] += window
        progress(i+1, len(starts))
    valid = slice(chunk, chunk+len(audio))
    if np.min(weight[valid]) <= 0:
        raise ValueError('Uncovered separation samples')
    return output[valid] / weight[valid]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--seconds', type=float)
    args = parser.parse_args()
    # Import only this upstream subpackage; unrelated TTS models require other runtimes.
    sys.path.insert(0, str(Path(site.getsitepackages()[0])/'mlx_audio/sts/models'))
    import mlx.core as mx
    from mel_roformer import MelRoFormer, MelRoFormerConfig
    config_data = json.loads((args.model/'config.json').read_text())
    config = MelRoFormerConfig(**{f.name: config_data[f.name] for f in dataclasses.fields(MelRoFormerConfig) if f.name in config_data})
    model = MelRoFormer(config)
    weights = mx.load(str(args.model/'model.safetensors'))
    # This conversion retains some PyTorch names. Apply the upstream mapping,
    # then reject every missing or unexpected parameter instead of using defaults.
    model.load_weights(list(model.sanitize(weights).items()), strict=True)
    model.eval()
    mx.eval(model.parameters())
    mx.set_cache_limit(256 * 1024**2)
    with sf.SoundFile(args.input) as source:
        if source.samplerate != config.sample_rate or source.channels != 2:
            raise ValueError('Worker requires decoded 44.1 kHz stereo audio')
        source.seek(round(args.start * source.samplerate))
        audio = source.read(round(args.seconds*source.samplerate) if args.seconds else -1, dtype='float32', always_2d=True)
    began = time.monotonic()
    def predict(chunk):
        out = model(mx.array(chunk.T[None]))
        mx.eval(out)
        return np.asarray(out[0].T, dtype=np.float32)
    def progress(done, total):
        print(json.dumps({'done': done, 'total': total, 'seconds': round(time.monotonic()-began, 2)}), flush=True)
    vocals = overlap_separate(audio, predict, config.chunk_size, config.chunk_size//config.num_overlap, progress)
    args.output.mkdir(parents=True, exist_ok=True)
    sf.write(args.output/'vocals.wav', vocals, config.sample_rate, subtype='FLOAT')
    sf.write(args.output/'instrumental.wav', audio-vocals, config.sample_rate, subtype='FLOAT')
    stats = {'model': 'mlx-community/mel-roformer-kim-vocal-2-mlx', 'runtime': 'mlx-audio==0.5.1',
             'revision': '64cbfcb004e39430e5f584552c05949440ec39ce',
             'frames': len(audio), 'sample_rate': config.sample_rate, 'chunk': config.chunk_size,
             'overlap': config.num_overlap, 'elapsed_seconds': round(time.monotonic()-began, 2),
             'peak_memory_gb': round(mx.get_peak_memory()/1024**3, 3),
             'mixture_error_max': float(np.max(abs(audio-(vocals+(audio-vocals)))))}
    (args.output/'separation.json').write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats), flush=True)


if __name__ == '__main__':
    main()
