import types
import sys
from pathlib import Path

# ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide a minimal stub for the mutagen.flac module used by ConcertTagger
mutagen = types.ModuleType('mutagen')
flac_mod = types.ModuleType('mutagen.flac')

class DummyInfo:
    length = 0
    md5_signature = b""
    bits_per_sample = 16
    sample_rate = 44100
    channels = 2


class DummyFLAC:
    def __init__(self, path):
        self.info = DummyInfo()

    def __contains__(self, item):
        return False

    def __getitem__(self, item):
        raise KeyError


flac_mod.FLAC = DummyFLAC
flac_mod.Picture = object
mutagen.flac = flac_mod
sys.modules.setdefault("mutagen", mutagen)
sys.modules.setdefault("mutagen.flac", flac_mod)

from tagger import ConcertTagger
from recordingfiles import RecordingFolder


def _make_tagger(folder: Path) -> ConcertTagger:
    tg = ConcertTagger.__new__(ConcertTagger)
    tg.config = {"cover": {"artwork_folders": {}, "default_images": {}}}
    tg.folderpath = folder
    tg.db = None
    tg.folder = RecordingFolder(str(folder))
    tg.etreerec = types.SimpleNamespace(artist_abbrev="gd")
    return tg


def test_standardize_folder_year_two_digit(tmp_path: Path):
    folder = tmp_path / "gd75-07-05.test"
    folder.mkdir()
    tagger = _make_tagger(folder)
    tagger._standardize_folder_year()
    assert tagger.folderpath.name.startswith("gd1975-")


def test_standardize_folder_year_already_four(tmp_path: Path):
    folder = tmp_path / "gd1975-07-05.test"
    folder.mkdir()
    tagger = _make_tagger(folder)
    tagger._standardize_folder_year()
    assert tagger.folderpath.name == "gd1975-07-05.test"


def test_standardize_folder_year_no_prefix(tmp_path: Path):
    folder = tmp_path / "ph75-07-05.test"
    folder.mkdir()
    tagger = _make_tagger(folder)
    tagger._standardize_folder_year()
    assert tagger.folderpath.name == folder.name

