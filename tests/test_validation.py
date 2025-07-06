import types
import sys
from pathlib import Path

# ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub mutagen.flac used by RecordingFolder
mutagen = types.ModuleType('mutagen')
flac_mod = types.ModuleType('mutagen.flac')
flac_mod.FLAC = object
flac_mod.Picture = object
mutagen.flac = flac_mod
sys.modules.setdefault('mutagen', mutagen)
sys.modules.setdefault('mutagen.flac', flac_mod)

from validation import check_and_rename
from recordingfiles import RecordingFolder

class DummyDB:
    def __init__(self):
        self.logged = []
    def insert_folder_shnid_log(self, shnid, folder_name):
        self.logged.append((shnid, folder_name))
    def close(self):
        pass


def test_check_and_rename_no_match(tmp_path, monkeypatch):
    folder = tmp_path / "gd75-07-05.sbd"
    folder.mkdir()

    def fake_find(self, db=None, debug=False):
        return None
    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", fake_find)

    db = DummyDB()
    new_folder, matched = check_and_rename(str(folder), db)
    assert not matched
    assert Path(new_folder) == folder


def test_check_and_rename_with_match(tmp_path, monkeypatch):
    folder = tmp_path / "gd75-07-05.sbd"
    folder.mkdir()

    def fake_find(self, db=None, debug=False):
        return types.SimpleNamespace(id=123, artist_abbrev="gd", date="1975-07-05")
    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", fake_find)

    db = DummyDB()
    new_folder, matched = check_and_rename(str(folder), db)
    assert matched
    assert (tmp_path / "gd1975-07-05.123.sbd").exists()
    assert Path(new_folder).name == "gd1975-07-05.123.sbd"
    assert db.logged and db.logged[0][0] == 123
