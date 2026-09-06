"""Use AutoMashup key/pitch helpers, preferring the local non-cloud installation."""
import sys
from .storage import ROOT, DATA

repository = DATA / 'automashup'
if not repository.exists():
    repository = ROOT / 'vendor/automashup'
sys.path.insert(0, str(repository / 'automashup'))
from automashup.src.key_finder import KeyFinder
from automashup.src.pitch_utils import semitones_between_keys
