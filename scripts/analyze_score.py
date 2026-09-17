"""Run the pinned SheetSage2 model in the isolated score runtime, offline."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--device', choices=('auto', 'cpu', 'mps', 'cuda'), default=os.getenv('MASHUP_SCORE_DEVICE', 'auto'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def status(percent, message):
        tmp = args.output / 'progress.tmp'
        tmp.write_text(json.dumps({'percent': percent, 'message': message}))
        tmp.replace(args.output / 'progress.json')
        print(json.dumps({'percent': percent, 'message': message}), flush=True)

    status(2, 'Musikmodell laden')
    import numpy as np
    import soundfile as sf
    import torch
    import mir_eval.chord
    from transformers import AutoModel
    torch.set_num_threads(4)
    device = args.device
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    model = AutoModel.from_pretrained(str(args.model), base_model_path=str(args.base),
                                     trust_remote_code=True, local_files_only=True).eval().to(device)
    audio, rate = sf.read(args.input, dtype='float32', always_2d=True)
    audio = audio.mean(axis=1)
    started = time.monotonic()

    def progress(update):
        stage = update['stage']
        window, windows = update.get('window', 1), update.get('windows', 1)
        base = 8 + 86*(window-1)/windows
        if stage == 'encoding':
            status(round(base), f'Songkontext erfassen · Abschnitt {window}/{windows}')
        elif stage == 'decoding':
            status(round(base + 80/windows*min(update['tokens']/5120, .99)),
                   f'Akkorde, Melodie und Struktur lesen · Abschnitt {window}/{windows}')
        elif stage == 'window_complete':
            status(round(8+86*window/windows), f'Abschnitt {window}/{windows} erkannt')

    result = model.transcribe(audio, sampling_rate=rate, output_dir=args.output, dtype='fp32', progress=progress,
                              prompts=('timestamp', 'downbeat_meter', 'structure', 'key', 'chord_full', 'melody_vocal'))
    events = result['events']
    duration = len(audio)/rate
    # Never extend a truncated prediction to the rest of the song.
    end_coverage = min(duration, max((e['time'] for e in events), default=0.) + 2.)
    profile = {'duration': duration, 'coverage_end': end_coverage, 'chords': [], 'melody': [], 'structure': [],
               'warnings': result.get('warnings', []), 'device': device, 'prompts': result['prompts'],
               'elapsed_seconds': round(time.monotonic()-started, 2)}
    for field, destination in (('chord', 'chords'), ('structure', 'structure')):
        rows = [e for e in events if field in e['values']]
        for index, event in enumerate(rows):
            start = max(0., float(event['time']))
            end = min(duration, float(rows[index+1]['time']) if index+1 < len(rows) else end_coverage)
            if end <= start:
                continue
            label = event['values'][field]
            row = {'start': start, 'end': end, 'label': label}
            if field == 'chord':
                try:
                    root, bitmap, _ = mir_eval.chord.encode(label)
                    if root < 0:
                        continue
                    row['chroma'] = np.roll(bitmap, root).astype(float).tolist()
                except mir_eval.chord.InvalidChordException:
                    continue
            if destination == 'structure' and profile[destination] and profile[destination][-1]['label'] == label:
                profile[destination][-1]['end'] = end
            else:
                profile[destination].append(row)
    for event in events:
        for note in event['values'].get('melody', []):
            if note['track'] != 0:
                continue
            start, end = max(0., float(event['time'])), min(duration, float(note['end_time']))
            if end > start and 0 <= int(note['pitch']) <= 127:
                profile['melody'].append({'start': start, 'end': end,
                                          'chroma': np.eye(12)[int(note['pitch']) % 12].tolist()})
    for field in ('chords', 'melody', 'structure'):
        profile[field].sort(key=lambda row: row['start'])
    (args.output / 'profile.json').write_text(json.dumps(profile, ensure_ascii=False))
    status(100, 'Akkorde und Songabschnitte fertig')


if __name__ == '__main__':
    main()
