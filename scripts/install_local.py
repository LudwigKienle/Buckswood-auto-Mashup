"""Copy application sources into local storage, keeping audio and models separate."""
import shutil
from studio.storage import ROOT, DATA

target = DATA / 'app'
if ROOT != target:
    for folder in ('studio', 'scripts', 'web/src', 'tests'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.sh', '.jsx', '.js', '.css'):
                dest = target / path.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
    for name in ('web/package.json', 'web/package-lock.json', 'web/vite.config.js',
                 'web/index.html', 'requirements.txt', 'requirements-hq.txt',
                 'requirements-dev.txt', 'pytest.ini', 'README.md', 'LICENSE',
                 'THIRD_PARTY_NOTICES.md', 'CONTRIBUTING.md', 'docs/quality.md'):
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    shutil.copytree(ROOT / 'LICENSES', target / 'LICENSES', dirs_exist_ok=True)
print(target)
