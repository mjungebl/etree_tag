import hashlib
import os
from types import SimpleNamespace

import pytest

from services import verification
from services.bootstrap import save_flac_path
from services.config import CONFIG_VERSION, load_app_config


@pytest.mark.parametrize(("platform", "command"), [("nt", "flac.exe"), ("posix", "flac")])
def test_flac_checks_config_then_path(platform, command, monkeypatch):
    candidates = []
    monkeypatch.setattr(verification, "os", SimpleNamespace(name=platform))

    def probe(candidate):
        candidates.append(candidate)
        return candidate if candidate == command else None

    monkeypatch.setattr(verification, "_working_flac", probe)
    assert verification.choose_flac("old-path", interactive=False) == command
    assert candidates == ["old-path", command]


def test_flac_download_menu_validates_entered_path(monkeypatch):
    answers = iter(["1", "2", "bad-path", "2", '"good path"'])
    opened = []
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(verification.webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(
        verification, "_working_flac",
        lambda path: path if path == "good path" else None,
    )
    assert verification.choose_flac(None, interactive=True) == "good path"
    assert opened == [verification.FLAC_DOWNLOADS]


def test_flac_menu_saves_working_path_for_next_run(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    original = f"config_version = {CONFIG_VERSION}\n[run]\nverify = true\n"
    config.write_bytes(original.encode())
    executable = str(tmp_path / "FLAC Tools" / "flac")
    answers = iter(["2", executable])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(verification, "_working_flac", lambda path: path if path == executable else None)

    assert verification.choose_flac(
        None, interactive=True, remember=lambda path: save_flac_path(config, path),
    ) == executable
    settings = load_app_config(config, user_config=True)
    assert settings.run.verify
    assert config.with_name(f"config.toml.v{CONFIG_VERSION}.bak").read_bytes() == original.encode()
    assert verification.choose_flac(settings.supportfiles.files["flac"], interactive=True) == executable


def test_flac_missing_defaults_to_exit(monkeypatch):
    monkeypatch.setattr(verification, "_working_flac", lambda path: None)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert verification.choose_flac(None, interactive=True) is None


def test_flac_accepts_installation_directory(tmp_path, monkeypatch):
    executable = tmp_path / ("flac.exe" if os.name == "nt" else "flac")
    executable.touch()
    monkeypatch.setattr(verification.shutil, "which", lambda path: path)

    def run(args, **kwargs):
        assert args == [str(executable), "--version"]
        return SimpleNamespace(returncode=0, stdout=b"flac 1.5.0\n")

    monkeypatch.setattr(verification.subprocess, "run", run)
    assert verification.choose_flac(str(tmp_path), interactive=False) == str(executable)


def test_shn_md5_without_external_tool(tmp_path):
    shn = tmp_path / "track.shn"
    shn.write_bytes(b"recording")
    progress = []
    assert verification.verify_show(tmp_path, None, progress=progress.append) == [
        "Unverified: track.shn has no MD5 entry.",
    ]
    assert "SHN MD5 check [Unverified]" in progress[-1]
    digest = hashlib.md5(shn.read_bytes(), usedforsecurity=False).hexdigest()
    (tmp_path / "show.md5").write_text(f"{digest} *track.shn\n", encoding="utf-8")
    assert verification.verify_show(tmp_path, None, progress=progress.append) == [
        "Verified whole-file MD5 for 1 SHN file(s).",
    ]
    assert "SHN MD5 check [OK]" in progress[-1]
    shn.write_bytes(b"damaged")
    with pytest.raises(verification.VerificationFailed, match="MD5 mismatch"):
        verification.verify_show(tmp_path, None, progress=progress.append)
    assert "SHN MD5 check [Failed]" in progress[-1]
    assert "MD5 mismatch" in progress[-1]


def test_verification_receipt_reuses_only_unchanged_shn_inputs(tmp_path):
    shn = tmp_path / "track.shn"
    shn.write_bytes(b"original")
    nested = tmp_path / "disc2"
    nested.mkdir()
    companion = nested / "track.shn"
    companion.write_bytes(b"original")
    manifest = tmp_path / "show.md5"
    digest = hashlib.md5(shn.read_bytes(), usedforsecurity=False).hexdigest()
    manifest.write_text(f"{digest} *track.shn\n{digest} *disc2/track.shn\n", encoding="utf-8")
    progress = []

    def get_flac():
        pytest.fail("SHN checks do not need FLAC")

    def verify():
        return verification.verify_show_with_receipt(tmp_path, get_flac, progress=progress.append)

    assert verify() == ["Verified whole-file MD5 for 2 SHN file(s)."]
    assert (tmp_path / verification.VERIFICATION_RECEIPT).is_file()
    assert verify()[0].startswith("Reused verification from ")
    assert progress[-1].startswith("Reused verification from ")
    companion.write_bytes(b"damaged audio")
    with pytest.raises(verification.VerificationFailed, match="MD5 mismatch"):
        verify()


def test_flac_decoder_failure_blocks_show(tmp_path, monkeypatch):
    tracks = [tmp_path / name for name in ("track1.flac", "track2.flac")]
    for track in tracks:
        track.touch()
    progress = []

    def run(args, **kwargs):
        assert args[:3] == ["flac", "-t", "--silent"]
        assert args[-1] in list(map(str, tracks))
        return SimpleNamespace(returncode=1, stderr=b"MD5 signature mismatch")

    monkeypatch.setattr(verification.subprocess, "run", run)
    with pytest.raises(verification.VerificationFailed, match="does not match its stored MD5"):
        verification.verify_show(tmp_path, "flac", progress=progress.append)
    assert len(progress) == 1
    assert progress[0].splitlines() == [
        "Verification [Failed]",
        "  - track1.flac: decoded audio does not match its stored MD5",
        "  - track2.flac: decoded audio does not match its stored MD5",
    ]
