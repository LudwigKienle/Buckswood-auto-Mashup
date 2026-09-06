"""Pinned public model download, with SHA256 verification. Never uploads audio."""
import hashlib
import os
import subprocess
from pathlib import Path
from studio.storage import DATA

REPO = 'mlx-community/mel-roformer-kim-vocal-2-mlx'
REVISION = '64cbfcb004e39430e5f584552c05949440ec39ce'
SHA256 = '312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5'


def main():
    folder = DATA/'models/mel-roformer-kim-vocal-2'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/'model.safetensors'
    if target.exists() and (folder/'config.json').exists():
        with target.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() == SHA256:
                print('Verified RoFormer model already installed')
                return
    command = [str(DATA/'separation-runtime/bin/hf'), 'download', REPO, '--revision', REVISION,
               '--local-dir', str(folder), '--include', '*.json', '--include', '*.safetensors',
               '--include', 'LICENSE', '--include', 'README.md']
    result = subprocess.run(command, env={**os.environ, 'HF_HUB_DISABLE_XET': '1'}, capture_output=True, text=True)
    if result.returncode:
        print('Hub download failed; retrying pinned public files with the macOS certificate store.', flush=True)
        for name in ('config.json', 'LICENSE', 'README.md', 'model.safetensors'):
            part = folder/(name+'.download')
            subprocess.run(['curl', '-fsSL', '--retry', '2',
                            f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}?download=true',
                            '-o', str(part)], check=True)
            part.replace(folder/name)
    with target.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != SHA256:
            target.rename(folder/'model.invalid')
            raise RuntimeError('Model checksum mismatch. Invalid download was not activated.')
    (folder/'revision.txt').write_text(REVISION+'\n'+SHA256+'\n')
    print('RoFormer model SHA256 verified')


if __name__ == '__main__':
    main()
