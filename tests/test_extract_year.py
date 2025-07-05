import sys
import types
from pathlib import Path

# ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide a minimal stub for the mutagen.flac module used by tagger
mutagen = types.ModuleType('mutagen')
flac_mod = types.ModuleType('mutagen.flac')
flac_mod.FLAC = object
flac_mod.Picture = object
mutagen.flac = flac_mod
sys.modules.setdefault('mutagen', mutagen)
sys.modules.setdefault('mutagen.flac', flac_mod)
tqdm_mod = types.ModuleType('tqdm')
tqdm_mod.tqdm = lambda x=None, **k: x
sys.modules.setdefault('tqdm', tqdm_mod)

from tagger import extract_year


def test_extract_year_iso():
    assert extract_year("1975-06-21") == 1975


def test_extract_year_partial_dashes():
    assert extract_year("1975-XX-XX") == 1975


def test_extract_year_partial_question():
    assert extract_year("??/??/75") == 1975
