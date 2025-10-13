import types
import sys
from pathlib import Path
from tagger import ConcertTagger
from recordingfiles import RecordingFolder

# ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide a minimal stub for the mutagen.flac module used by ConcertTagger
mutagen = types.ModuleType("mutagen")
flac_mod = types.ModuleType("mutagen.flac")


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


# Stub out tqdm to avoid dependency during tests
tqdm_mod = types.ModuleType("tqdm")
tqdm_mod.tqdm = lambda x=None, **k: x
sys.modules.setdefault("tqdm", tqdm_mod)




def _make_tagger(
    folder: Path, date="1975-07-05", shnid=12345, abbr="gd", standardize_artist_abbrev=None
) -> ConcertTagger:
    tg = ConcertTagger.__new__(ConcertTagger)
    tg.config = {"cover": {"artwork_folders": {}, "default_images": {}}}
    tg.folderpath = folder
    tg.db = None
    tg.folder = RecordingFolder(str(folder), standardize_artist_abbrev=standardize_artist_abbrev)
    tg.etreerec = types.SimpleNamespace(artist_abbrev=abbr, id=shnid, date=date)
    return tg


def test_standardize_folder_year_two_digit(tmp_path: Path):
    folder = tmp_path / "gd75-07-05.test"
    folder.mkdir()
    tagger = _make_tagger(folder)
    tagger.folder._standardize_folder_year(tagger.etreerec)
    tagger.folderpath = tagger.folder.folder
    assert tagger.folderpath.name.startswith("gd1975-")


def test_standardize_folder_year_already_four(tmp_path: Path):
    folder = tmp_path / "gd1975-07-05.test"
    folder.mkdir()
    tagger = _make_tagger(folder)
    tagger.folder._standardize_folder_year(tagger.etreerec)
    tagger.folderpath = tagger.folder.folder
    assert tagger.folderpath.name == "gd1975-07-05.12345.test"


def test_standardize_folder_year_no_prefix(tmp_path: Path):
    folder = tmp_path / "ph75-07-05.test"
    folder.mkdir()
    tagger = _make_tagger(folder)
    tagger.folder._standardize_folder_year(tagger.etreerec)
    tagger.folderpath = tagger.folder.folder
    assert tagger.folderpath.name == folder.name


def test_date_correction_and_shnid_insert(tmp_path: Path):
    folder = tmp_path / "gd1975-07-04.sbd"
    folder.mkdir()
    tagger = _make_tagger(folder, date="1975-07-05", shnid=999)
    tagger.folder._standardize_folder_year(tagger.etreerec)
    tagger.folderpath = tagger.folder.folder
    assert tagger.folderpath.name == "gd1975-07-05.999.sbd"


def test_move_existing_shnid(tmp_path: Path):
    folder = tmp_path / "gd1975-07-05.sbd.777.flac16"
    folder.mkdir()
    tagger = _make_tagger(folder, shnid=777)
    tagger.folder._standardize_folder_year(tagger.etreerec)
    tagger.folderpath = tagger.folder.folder
    assert tagger.folderpath.name == "gd1975-07-05.777.sbd.flac16"


def test_standardize_folder_year_with_alias(tmp_path: Path):
    folder = tmp_path / "jg+jk1975-07-05.sbd"
    folder.mkdir()
    overrides = {"jg": ["jgb", "jg+jk", "jgms"]}
    tagger = _make_tagger(
        folder,
        shnid=222,
        abbr="jg",
        standardize_artist_abbrev=overrides,
    )
    tagger.folder._standardize_folder_year(tagger.etreerec)
    tagger.folderpath = tagger.folder.folder
    assert tagger.folderpath.name == "jg1975-07-05.222.jg+jk.sbd"
