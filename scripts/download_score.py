"""Download pinned official snapshots; publish readiness only after hash checks."""
import hashlib
import json
from huggingface_hub import snapshot_download
from studio.storage import DATA, save_json

MODEL_REVISION = 'cd2f39b3b807b81f6e32bbb8ea6011da40f77649'
BASE_REVISION = 'd8ba1c745e733b3908ce6ad16ebeb17ac7600a42'


def verify(folder, expected):
    digest = hashlib.sha256()
    with (folder / 'model.safetensors').open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f'Model checksum mismatch: {folder.name}')


def main():
    # Weight licenses apply separately from this repository's GPL source code.
    print('SheetSage2 and MERT-v2 model weights: CC BY-NC 4.0. See the model cards and THIRD_PARTY_NOTICES.md.')
    for name, folder, revision in [('SheetSage2', 'sheetsage2', MODEL_REVISION),
                                    ('MERT-v2-FullSong', 'mert-v2', BASE_REVISION)]:
        snapshot_download('m-a-p/' + name, revision=revision, local_dir=DATA / 'models' / folder,
                          allow_patterns=['*.py', '*.json', '*.safetensors', '*.txt', '*.md', 'LICENSE'],
                          ignore_patterns=['assets/*', 'render_assets/*'])
    model, base = DATA / 'models/sheetsage2', DATA / 'models/mert-v2'
    config = json.loads((model / 'config.json').read_text())
    if config['base_model_revision'] != BASE_REVISION:
        raise ValueError('Unexpected SheetSage2 parent revision')
    verify(base, config['base_model_sha256'])
    digest = 'b235f68091a5f5b644000f2b5acb57d1e70432aca2b34ab1b9cf27236e1f4274'
    verify(model, digest)
    save_json(model / 'buckswood-install.json', {'model_revision': MODEL_REVISION,
              'base_revision': BASE_REVISION, 'adapter_sha256': digest})
    print('Pinned model snapshots are ready for offline inference.')


if __name__ == '__main__':
    main()
