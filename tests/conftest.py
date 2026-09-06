"""Never read or mutate a user's tracks, exports or jobs during tests."""
import os
import tempfile
from pathlib import Path

_resources = Path(os.environ.get('MASHUP_DATA', Path.home() / 'Library/Application Support/Mashup Studio'))
_sandbox = tempfile.TemporaryDirectory(prefix='buckswood-tests-')
for name in ('automashup', 'rubberband-build'):
    source = _resources / name
    if source.exists():
        (Path(_sandbox.name) / name).symlink_to(source.resolve(), target_is_directory=True)
os.environ['MASHUP_DATA'] = _sandbox.name


def pytest_unconfigure(config):
    _sandbox.cleanup()
