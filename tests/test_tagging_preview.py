import hashlib
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from mutagen.flac import FLAC

import cli
import lcdb_graphql
from recordingfiles import RecordingFolder
from services import shn_conversion
from services.config import SHIPPED_CONFIG
from services.verification import VerificationFailed


@pytest.fixture
def recording(tmp_path, monkeypatch):
    folder = tmp_path / "gd74-06-28"
    folder.mkdir()
    flac = folder / "track.flac"
    streaminfo = struct.pack(
        ">HH6xQ16x", 16, 16, (44100 << 44) | (1 << 41) | (15 << 36) | 16,
    )
    flac.write_bytes(b"fLaC\x80\x00\x00\x22" + streaminfo)
    audio = FLAC(flac)
    audio["album"] = "Old album"
    audio["custom"] = "Remove this tag"
    audio.save()
    database = SimpleNamespace(
        close=lambda: None, pending_remote_shnids=[],
        conn=SimpleNamespace(rollback=lambda: None),
    )
    monkeypatch.setattr(cli, "SQLiteEtreeDB", lambda path: database)
    track = SimpleNamespace(title="New title", gazinta=False, disc="1", tracknum="01")
    match = SimpleNamespace(
        id=1234, date="1974-06-28", artist="Grateful Dead", artist_abbrev="gd",
        city="Boston, MA", etreevenue="Boston Garden", source="Source notes",
        tracks=[track], get_track_by_checksum=lambda checksum: track,
    )
    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", lambda self, **kwargs: match)
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"cover bytes")
    (folder / "folder.jpg").write_bytes(b"old cover")
    monkeypatch.setattr(cli.ConcertTagger, "_find_artwork", lambda *args: image)
    config = tmp_path / "config.toml"
    config.write_text(
        SHIPPED_CONFIG.read_text(encoding="utf-8")
        .replace("clear_existing_artwork = false", "clear_existing_artwork = true"),
        encoding="utf-8",
    )
    args = ["--config", str(config), "--database", str(tmp_path / "db"), "--clear-tags"]
    yield folder, flac, args
    for handler in cli.logging.getLogger().handlers[:]:
        if isinstance(handler, cli.logging.FileHandler) and Path(handler.baseFilename).is_relative_to(tmp_path):
            cli.logging.getLogger().removeHandler(handler)
            handler.close()


@pytest.mark.parametrize("answer", ["", "y", "Yes", " yes", "yes ", None])
def test_preview_applies_only_exact_yes(recording, monkeypatch, answer):
    folder, flac, args = recording
    original = flac.read_bytes()

    def decline(prompt):
        manifest = next(folder.glob("tagger_logs/*_changes.txt")).read_text(encoding="utf-8")
        assert "ALBUM: ['Old album'] ->" in manifest
        assert "CUSTOM: ['Remove this tag'] -> None" in manifest
        assert "Back up folder.jpg as folder.jpg.old" in manifest
        assert "Rename folder to" in manifest
        assert flac.read_bytes() == original
        assert (folder / "folder.jpg").read_bytes() == b"old cover"
        if answer is None:
            raise EOFError
        return answer

    monkeypatch.setattr("builtins.input", decline)
    assert cli.main([*args, str(folder)]) == 0
    assert flac.read_bytes() == original
    assert (folder / "folder.jpg").read_bytes() == b"old cover"
    assert not (folder / "folder.jpg.old").exists()


def test_yes_applies_reviewed_plan_and_second_run_skips_writes(recording, monkeypatch, capsys):
    folder, _, args = recording
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert cli.main([*args, str(folder)]) == 0
    renamed = folder.with_name("gd1974-06-28.1234")
    flac = renamed / "track.flac"
    audio = FLAC(flac)
    assert audio["title"] == ["New title"]
    assert "custom" not in audio
    assert audio.pictures[0].data == b"cover bytes"
    assert (renamed / "folder.jpg.old").read_bytes() == b"old cover"
    original_mtime = flac.stat().st_mtime_ns
    manifests = set(renamed.glob("tagger_logs/*_changes.txt"))
    assert len(manifests) == 1
    capsys.readouterr()

    def unexpected_prompt(prompt):
        pytest.fail("Already current recordings should not prompt")

    monkeypatch.setattr("builtins.input", unexpected_prompt)
    assert cli.main([*args, str(renamed)]) == 0
    assert flac.stat().st_mtime_ns == original_mtime
    assert set(renamed.glob("tagger_logs/*_changes.txt")) == manifests
    assert capsys.readouterr().out.strip() == (
        "Tagging results\n  Updated: 0\n  Already tagged per preferences: 1\n"
        "  Failed: 0\n\nNo changes detected."
    )


def test_yes_skips_show_if_flac_changed_after_preview(recording, monkeypatch, capsys):
    folder, flac, args = recording

    def modify_and_approve(prompt):
        audio = FLAC(flac)
        audio["album"] = "External edit"
        audio.save()
        return "yes"

    monkeypatch.setattr("builtins.input", modify_and_approve)
    assert cli.main([*args, str(folder)]) == 0
    assert FLAC(flac)["album"] == ["External edit"]
    assert not (folder / "folder.jpg.old").exists()
    assert (
        "Tagging results\n  Updated: 0\n"
        "  Already tagged per preferences: 0\n  Failed: 1"
        in capsys.readouterr().out
    )


def test_mixed_preview_summarizes_outcomes_and_keeps_traceback_in_log(
    recording, monkeypatch, capsys,
):
    folder, flac, args = recording
    original = flac.read_bytes()
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert cli.main([*args, str(folder)]) == 0
    capsys.readouterr()
    current = folder.with_name("gd1974-06-28.1234")
    changing = folder.with_name("gd74-06-28.sbd")
    unmatched = folder.with_name("no-catalog-match")
    unreachable = folder.with_name("remote-lookup")
    for candidate in (changing, unmatched, unreachable):
        candidate.mkdir()
        (candidate / "track.flac").write_bytes(original)

    response = requests.Response()
    response.status_code = 200
    response._content = b"<html>Etree unavailable</html>"
    monkeypatch.setattr(lcdb_graphql.requests, "post", lambda *args, **kwargs: response)
    original_match = RecordingFolder._find_matching_recording

    def match(self, **kwargs):
        if self.folder == unreachable:
            lcdb_graphql.find_shnid_by_checksum(self.checksums[0])
        if self.folder == unmatched:
            return None
        return original_match(self, **kwargs)

    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", match)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    log = folder.parent / "mixed.log"
    folders = [str(path) for path in (current, changing, unmatched, unreachable)]
    assert cli.main([*args, "--log-file", str(log), *folders]) == 1

    output = capsys.readouterr()
    expected_summary = (
        "Will change: 1\n"
        "  Already tagged per preferences: 1\n"
        "  Expected to fail: 2\n\n"
        "    - no-catalog-match\n"
        "      No catalog recording matched the audio fingerprints.\n\n"
        "    - remote-lookup\n"
        "      Etree catalog returned a response that was not valid JSON"
    )
    assert expected_summary in output.out
    assert "\n\nExample FLAC tags for gd74-06-28.sbd/track.flac\n" in output.out
    assert "  Song title: New title\n" in output.out
    assert "  Write DATE tag: No\n" in output.out
    assert "  Write separate YEAR, MONTH, and DAY tags: No\n" in output.out
    assert "  Clear existing tags: Yes\n\nChange manifest:" in output.out
    assert output.err == ""
    manifest = next(folder.parent.glob("*_changes.txt")).read_text(encoding="utf-8")
    assert expected_summary in manifest
    assert "Example FLAC tags for gd74-06-28.sbd/track.flac" in manifest
    assert "Traceback" not in manifest
    assert "Traceback" in next(folder.parent.glob("*_mixed.log")).read_text()
    assert (changing / "track.flac").read_bytes() == original


def test_verification_failure_blocks_show_before_catalog_lookup(recording, monkeypatch, capsys):
    folder, flac, args = recording
    original = flac.read_bytes()
    monkeypatch.setattr(cli, "choose_flac", lambda *args, **kwargs: "flac")

    def bad_audio(folder, executable, *, progress):
        assert executable == "flac"
        raise VerificationFailed("track.flac: FLAC audio test failed")

    def unexpected_match(*args, **kwargs):
        pytest.fail("A show that failed verification should not reach catalog lookup")

    monkeypatch.setattr(cli, "verify_show", bad_audio)
    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", unexpected_match)
    monkeypatch.setattr("builtins.input", unexpected_match)
    assert cli.main([*args, "--verify", str(folder)]) == 1
    assert "  Failed: 1" in capsys.readouterr().out
    assert flac.read_bytes() == original
    assert not list(folder.glob("tagger_logs/*_changes.txt"))


@pytest.mark.parametrize(("verify", "reuse"), [(False, False), (True, False), (True, True)])
def test_shn_only_set_is_reported_separately(recording, monkeypatch, capsys, verify, reuse):
    folder, flac, args = recording
    flac.unlink()
    shn = folder / "track.shn"
    shn.write_bytes(b"recording")
    digest = hashlib.md5(shn.read_bytes(), usedforsecurity=False).hexdigest()
    (folder / "show.md5").write_text(f"{digest} *track.shn\n", encoding="utf-8")

    def unexpected(*args, **kwargs):
        pytest.fail("SHN-only sets do not need FLAC or a catalog match")

    monkeypatch.setattr(cli, "choose_flac", unexpected)
    monkeypatch.setattr(RecordingFolder, "_find_matching_recording", unexpected)
    monkeypatch.setattr("builtins.input", unexpected)
    if reuse:
        with Path(args[1]).open("a", encoding="utf-8") as config:
            config.write("\n[run]\nverify = true\nreuse_verification = true\n")
    elif verify:
        args.append("--verify")
    assert cli.main([*args, str(folder)]) == 0
    output = capsys.readouterr().out
    assert "  Failed: 0" in output
    assert "  SHN-only sets skipped for tagging: 1\n  Failed: 0" in output
    assert ("Verifying file integrity..." in output) == verify
    if verify:
        assert output.index("Verifying file integrity...") < output.index("Checking available SHN MD5s")
    assert "SHN-only sets (verification only)" in output
    assert f"[{'OK' if verify else 'Not checked'}] {folder.name}" in output
    assert ("Verified whole-file MD5" if verify else "Verification is off") in output
    if reuse:
        assert cli.main([*args, str(folder)]) == 0
        assert "Reused verification from " in capsys.readouterr().out
        assert cli.main([*args, "--no-reuse-verification", str(folder)]) == 0
        assert "Checking available SHN MD5s" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["normal", "paranoid", "mismatch", "declined"])
def test_shn_conversion_precedes_verification_and_tagging(recording, monkeypatch, capsys, mode):
    folder, flac, args = recording
    folder_with_id = folder.with_name(f"{folder.name}.01234.shnf")
    folder.rename(folder_with_id)
    folder = folder_with_id
    flac = folder / flac.name
    audio = flac.read_bytes()
    flac.unlink()
    shn = folder / "track.shn"
    shn.write_bytes(b"original SHN")
    digest = hashlib.md5(shn.read_bytes(), usedforsecurity=False).hexdigest()
    checksum = f"{digest} *{shn.name}\n".encode()
    manifest = folder / "original.md5"
    manifest.write_bytes(checksum)
    marker = folder / "SHN-to-FLAC-1234.txt"
    archive = folder / "_shn_source"
    extras = folder / "extras"
    extras.mkdir()
    (extras / "notes.txt").write_bytes(b"original notes")
    info = folder / "info.txt"
    info.write_bytes(b"original show info")
    (folder / "old.log").write_bytes(b"old log")
    config = Path(args[1])
    if mode in {"paranoid", "mismatch"}:
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "enabled = false\ncompression_level = 8\nparanoid = false",
                "enabled = true\ncompression_level = 5\nparanoid = true",
            ),
            encoding="utf-8",
        )

    def encode(command, **kwargs):
        assert mode != "declined", "Conversion started without approval"
        if "-hash" in command:
            is_shn = command[command.index("-f") + 1] == "shn"
            if is_shn:
                assert Path(command[command.index("-i") + 1]).read_bytes() == b"original SHN"
            digest = b"other" if mode == "mismatch" and not is_shn else b"same"
            return SimpleNamespace(returncode=0, stdout=b"SHA256=" + digest)
        source = Path(command[command.index("-i") + 1])
        assert source.name == shn.name
        assert source.parent == folder if mode == "normal" else source.parent.name == archive.name
        assert command[command.index("-compression_level") + 1] == ("8" if mode == "normal" else "5")
        Path(command[-1]).write_bytes(audio)
        return SimpleNamespace(returncode=0)

    def verify_published(path, executable, *, progress):
        assert path == folder
        assert flac.read_bytes() == audio
        assert "track.shn -> track.flac" in marker.read_text(encoding="utf-8")
        return []

    monkeypatch.setattr(cli, "choose_flac", lambda *args, **kwargs: "flac")
    monkeypatch.setattr(cli.shutil, "which", lambda command: "ffmpeg")
    monkeypatch.setattr(shn_conversion.subprocess, "run", encode)
    monkeypatch.setattr(shn_conversion, "verify_show", lambda path, executable, **kwargs: [])
    monkeypatch.setattr(cli, "verify_show", verify_published)
    def approve(prompt):
        if "apply SHN conversions" not in prompt:
            return ""
        change_manifest, = folder.rglob("*.shn-conversion.txt")
        text = change_manifest.read_text(encoding="utf-8")
        assert "track.shn -> track.flac" in text
        if mode in {"normal", "declined"}:
            assert "Rename original.md5 to original.md5.shn-source" in text
        assert shn.exists() and not flac.exists() and not marker.exists()
        return "" if mode == "declined" else "yes"

    monkeypatch.setattr("builtins.input", approve)
    override = ["--convert-shn"] if mode in {"normal", "declined"} else []
    result = cli.main([*args, *override, "--verify", str(folder)])
    if mode == "declined":
        assert result == 0
        assert "No SHN conversions or tagging changes were applied" in capsys.readouterr().out
        assert shn.exists() and manifest.read_bytes() == checksum
        assert not any(path.exists() for path in (archive, flac, marker))
        return
    if mode == "mismatch":
        assert result == 1
        assert "decoded SHN and FLAC audio differ" in capsys.readouterr().out
        assert not any(path.exists() for path in (archive, flac, marker))
        assert manifest.read_bytes() == checksum
        return
    assert result == 0
    output = capsys.readouterr().out
    assert "Will change: 1" in output
    assert "Converting SHN 1/1" in output
    assert flac.read_bytes() == audio
    assert RecordingFolder(str(folder)).info_file == info
    if mode == "paranoid":
        assert manifest.read_bytes() == checksum
        assert shn.read_bytes() == b"original SHN"
        assert (archive / shn.name).read_bytes() == shn.read_bytes()
        assert (archive / manifest.name).read_bytes() == checksum
        assert (archive / info.name).read_bytes() == info.read_bytes()
        assert (archive / "extras" / "notes.txt").read_bytes() == b"original notes"
        assert list(archive.rglob("*.log")) == [archive / "old.log"]
        assert (archive / "old.log").read_bytes() == b"old log"
        assert not list(archive.rglob("*.shn-conversion.txt"))
        assert "Saving the verified original fileset in _shn_source" in output
    else:
        assert not manifest.exists()
        assert manifest.with_suffix(".md5.shn-source").read_bytes() == checksum
        assert not archive.exists()
        assert not shn.exists()
        assert (extras / "notes.txt").read_bytes() == b"original notes"
        assert "Removing 1 source SHN file(s) after FLAC verification" in output
