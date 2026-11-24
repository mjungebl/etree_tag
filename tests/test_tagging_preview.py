import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from mutagen.flac import FLAC

import cli
import lcdb_graphql
from recordingfiles import RecordingFolder
from services.config import SHIPPED_CONFIG


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
