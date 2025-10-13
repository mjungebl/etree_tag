import types
from pathlib import Path

import validation
from validation import check_and_rename, validate_parent_folder
from recordingfiles import RecordingFolder


class DummyDB:
    def __init__(self, *args, **kwargs):
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
    new_folder, matched, errors = check_and_rename(str(folder), db)
    assert not matched
    assert Path(new_folder) == folder
    assert errors == []



def test_check_and_rename_with_match(tmp_path, monkeypatch):
    folder = tmp_path / "gd75-07-05.sbd"
    folder.mkdir()

    def fake_find(self, db=None, debug=False):
        return types.SimpleNamespace(id=123, artist_abbrev="gd", date="1975-07-05")

    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", fake_find)

    def fake_verify(self):
        return [], []

    monkeypatch.setattr(RecordingFolder, "verify_fingerprint", fake_verify)

    db = DummyDB()
    new_folder, matched, errors = check_and_rename(str(folder), db)
    assert matched
    assert (tmp_path / "gd1975-07-05.123.sbd").exists()
    assert Path(new_folder).name == "gd1975-07-05.123.sbd"
    assert db.logged and db.logged[0][0] == 123
    assert errors == []



def test_check_and_rename_with_alias_prefix(tmp_path, monkeypatch):
    folder = tmp_path / "jg+jk1991-03-02.sbd"
    folder.mkdir()

    def fake_find(self, db=None, debug=False):
        return types.SimpleNamespace(id=222, artist_abbrev="jg", date="1991-03-02")

    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", fake_find)

    def fake_verify(self):
        return [], []

    monkeypatch.setattr(RecordingFolder, "verify_fingerprint", fake_verify)

    db = DummyDB()
    alias_overrides = {"jg": ["jg+jk", "jgb"]}
    new_folder, matched, errors = check_and_rename(
        str(folder),
        db,
        standardize_artist_abbrev=alias_overrides,
    )
    assert matched
    renamed = folder.parent / "jg1991-03-02.222.jg+jk.sbd"
    assert renamed.exists()
    assert Path(new_folder) == renamed
    assert errors == []



def test_check_and_rename_with_db_alias(tmp_path, monkeypatch):
    folder = tmp_path / "jg81-08-06.test"
    folder.mkdir()

    def fake_find(self, db=None, debug=False):
        return types.SimpleNamespace(id=333, artist_abbrev="jgb", date="1981-08-06")

    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", fake_find)

    def fake_verify(self):
        return [], []

    monkeypatch.setattr(RecordingFolder, "verify_fingerprint", fake_verify)

    db = DummyDB()
    alias_overrides = {"jg": ["jgb", "jg+jk"]}
    new_folder, matched, errors = check_and_rename(
        str(folder),
        db,
        standardize_artist_abbrev=alias_overrides,
    )
    assert matched
    renamed = folder.parent / "jg1981-08-06.333.jgb.test"
    assert renamed.exists()
    assert Path(new_folder) == renamed
    assert errors == []



def test_validate_parent_folder(tmp_path, monkeypatch):
    parent = tmp_path / "shows"
    sub1 = parent / "gd75-07-05.sbd"
    sub2 = parent / "gd76-07-05.sbd"
    sub1.mkdir(parents=True)
    sub2.mkdir()

    def fake_find(self, db=None, debug=False):
        if self.folder == sub1:
            return None
        return types.SimpleNamespace(id=456, artist_abbrev="gd", date="1976-07-05")

    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", fake_find)

    def fake_verify(self):
        return [], []

    monkeypatch.setattr(RecordingFolder, "verify_fingerprint", fake_verify)
    monkeypatch.setattr(validation, "SQLiteEtreeDB", DummyDB)

    results = validate_parent_folder(str(parent))
    assert results[0] == (str(sub1), False, [])
    renamed = parent / "gd1976-07-05.456.sbd"
    assert results[1] == (str(renamed), True, [])
    assert renamed.exists()
