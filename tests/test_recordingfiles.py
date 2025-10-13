import types
from pathlib import Path

import recordingfiles
from recordingfiles import RecordingFolder

def _create_sample_files(base: Path, info_name="info.txt"):
    (base / info_name).write_text("info contents", encoding="utf-8")
    (base / "example.ffp").write_text("fingerprint data", encoding="utf-8")
    (base / "checks.st5").write_text("checksum data", encoding="utf-8")


def test_read_methods_with_info_keyword(tmp_path: Path):
    _create_sample_files(tmp_path)
    rec = RecordingFolder(str(tmp_path))
    assert rec.read_info() == "info contents"
    assert rec.read_fingerprint() == "fingerprint data"
    assert rec.read_checksums() == "checksum data"


def test_fallback_txt_detection(tmp_path: Path):
    _create_sample_files(tmp_path, info_name="notes.txt")
    rec = RecordingFolder(str(tmp_path))
    # Should fall back to the only txt file
    assert rec.info_file.name == "notes.txt"
    assert rec.read_info() == "info contents"


def test_verify_fingerprint_existing(tmp_path, monkeypatch):
    ffp_file = tmp_path / "check.ffp"
    ffp_file.write_text("dummy")
    rec = RecordingFolder(str(tmp_path))

    calls = []

    class DummyFfp:
        def __init__(
            self, loc, name, signatures=None, metaflacpath=None, flacpath=None
        ):
            calls.append(("init", loc, name, signatures))
            self.result = ["ok"]
            self.errors = ["err"]

        def readffpfile(self):
            calls.append("read")

        def verify(self):
            calls.append("verify")

    monkeypatch.setattr(recordingfiles, "ffp", DummyFfp)

    result, errors = rec.verify_fingerprint()
    assert calls == [("init", str(tmp_path), "check.ffp", None), "read", "verify"]
    assert result == ["ok"]
    assert errors == ["err"]


def test_verify_fingerprint_generate(tmp_path, monkeypatch):
    rec = RecordingFolder(str(tmp_path))
    rec.musicfiles = [
        types.SimpleNamespace(name="a.flac", checksum="111"),
        types.SimpleNamespace(name="b.flac", checksum="222"),
    ]

    calls = []

    class DummyFfp:
        def __init__(
            self, loc, name, signatures=None, metaflacpath=None, flacpath=None
        ):
            self.signatures = signatures or {}
            self.result = ["ok"]
            self.errors = []
            calls.append(("init", loc, name, dict(self.signatures)))

        def SaveFfp(self):
            calls.append("save")

        def verify(self):
            calls.append("verify")

    monkeypatch.setattr(recordingfiles, "ffp", DummyFfp)

    result, errors = rec.verify_fingerprint()
    expected_file = tmp_path / f"{tmp_path.name}.ffp"
    assert rec.fingerprint_file == expected_file
    assert ("save" in calls) and ("verify" in calls)
    assert result == ["ok"]
    assert errors == []
