from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import cli
from services import bootstrap, config as config_service
from services.bootstrap import _ask_tagging_preferences
from services.config import SHIPPED_CONFIG, load_app_config
from services.tagging import performance_date_tags, tag_file_worker


def test_first_run_only_saves_config_and_next_run_uses_preferences(
    tmp_path, monkeypatch, capsys
):
    config_path = tmp_path / "prefs" / "config.toml"
    show = tmp_path / "show"
    show.mkdir()
    database = tmp_path / "catalog.db"
    log = show / "tagger_logs" / "tag_log.log"
    answers = iter(
        [str(show), "no", str(database), "", "yes", "yes", "", "", "", ""] + [""] * 10
    )
    monkeypatch.setattr(cli, "user_config_path", lambda: config_path)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def answer(prompt):
        print(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", answer)
    calls = []
    db = SimpleNamespace(close=lambda: calls.append("closed"))
    monkeypatch.setattr(cli, "SQLiteEtreeDB", lambda path: calls.append(path) or db)
    monkeypatch.setattr(
        cli, "_configure_logging", lambda path, verbose: calls.append((path, verbose))
    )
    monkeypatch.setattr(
        cli.ConcertTagger,
        "tag_shows",
        lambda folders, db, config, **kwargs: calls.append((folders, kwargs)),
    )

    assert cli.main([]) == 0
    output = capsys.readouterr().out
    assert str(config_path) in output
    assert (
        f"SQLite catalog [currently {SHIPPED_CONFIG.parent / 'db/etree_scrape.db'}]"
        in output
    )
    assert "Fallback image for gd [currently " in output
    assert f"Base log file (each run adds a timestamp) [{log}]" in output
    assert "Enable verbose diagnostic logging [no]" in output
    assert (
        "Show or library folder [required]: \n"
        "Treat each direct subfolder as a show? "
        "Choose no if the above folder is a single show. [yes]: " in output
    )
    assert ": \n\nALBUM TAG" in output
    assert "1973-10-29 St. Louis, MO MTX (131409) [24-96]" in output
    assert "China Cat Sunflower >" in output
    assert calls == []
    assert list(show.iterdir()) == []
    config = load_app_config(config_path, user_config=True)
    assert config.raw["config_version"] == 2
    assert config.run.scan_subfolders is False
    assert config.preferences.verbose_logging is True
    assert config.preferences.segue_string == ">"
    assert config.preferences.write_date is False
    assert config.preferences.write_date_parts is False
    assert (
        Path(config.cover.default_images["gd"])
        == SHIPPED_CONFIG.parent / "GD_Art/default.jpg"
    )

    assert cli.main(["--no-clear-tags"]) == 0
    (actual_log, verbose), *remaining = calls
    actual_log = Path(actual_log)
    assert actual_log.parent == log.parent
    timestamp, filename = actual_log.name.rsplit("_tag_log.log", 1)
    assert filename == ""
    datetime.strptime(timestamp, "%Y-%m-%d_%H-%M-%S_%f")
    assert verbose is True
    assert remaining == [
        str(database),
        ([show.as_posix()], {"clear_existing_tags": False}),
        "closed",
    ]


def test_discovery_skips_log_directories(tmp_path):
    for name in ("tagger_logs", "custom_logs", "show"):
        (tmp_path / name).mkdir()
    args = cli.parse_args(["--parent-folder", str(tmp_path)])
    assert cli.gather_folders(args, tmp_path / "custom_logs") == [
        (tmp_path / "show").as_posix()
    ]


def test_versioned_config_resolves_path_origins_and_rejects_invalid_values(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'config_version = 2\n[run]\nlibrary_folder = "shows"\n', encoding="utf-8"
    )
    config = load_app_config(config_path, user_config=True)
    assert Path(config.run.library_folder) == tmp_path / "shows"
    assert (
        Path(config.cover.default_images["gd"])
        == SHIPPED_CONFIG.parent / "GD_Art/default.jpg"
    )

    config_path.write_text("config_version = 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported config_version"):
        load_app_config(config_path, user_config=True)

    config_path.write_text(
        'config_version = 2\n[run]\nclear_tags = "yes"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="run.clear_tags"):
        load_app_config(config_path, user_config=True)


def test_version_one_upgrade_keeps_saved_values_and_backs_up_original(
    tmp_path, monkeypatch, capsys
):
    config_path = tmp_path / "config.toml"
    original = (
        "# original file\nconfig_version = 1\n"
        '[run]\nlibrary_folder = "shows"\n'
        '[preferences]\nsegue_string = "~>"\nverbose_logging = true\n'
        "[album_tag]\ninclude_city = false\n"
        '[cover.default_images]\ngd = "my-cover.png"\n'
        '[work_notes]\nfiles = [{name = "a"}]\n'
    ).encode()
    config_path.write_bytes(original)
    existing_backup = config_path.with_name("config.toml.v1.bak")
    existing_backup.write_bytes(b"earlier backup")
    monkeypatch.setattr(cli, "user_config_path", lambda: config_path)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        cli, "SQLiteEtreeDB", lambda path: pytest.fail("Setup opened SQLite")
    )
    prompts = []
    answers = iter([""] * 9 + ["yes", "yes"])
    monkeypatch.setattr(
        "builtins.input", lambda prompt: prompts.append(prompt) or next(answers)
    )

    assert cli.main([]) == 0
    output = capsys.readouterr().out
    assert "version 1 to 2" in output
    assert f"Current config (version 1): {config_path}" in output
    assert "Updated config (version 2): same path" in output
    assert "adds choices for album tags, track titles, and performance dates" in output
    assert all(
        "catalog" not in prompt and "library folder" not in prompt for prompt in prompts
    )
    assert existing_backup.read_bytes() == b"earlier backup"
    assert config_path.with_name("config.toml.v1.bak.2").read_bytes() == original
    config = load_app_config(config_path, user_config=True)
    assert config.raw["config_version"] == 2
    assert config.raw["work_notes"]["files"] == [{"name": "a"}]
    assert Path(config.run.library_folder) == tmp_path / "shows"
    assert Path(config.cover.default_images["gd"]) == tmp_path / "my-cover.png"
    assert config.preferences.segue_string == "~>"
    assert config.preferences.verbose_logging
    assert not config.album_tag.include_city
    assert config.preferences.write_date and config.preferences.write_date_parts


def test_cancelled_upgrade_leaves_original_alone(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    original = b"config_version = 1\n"
    config_path.write_bytes(original)
    monkeypatch.setattr(cli, "user_config_path", lambda: config_path)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def cancel(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", cancel)
    assert cli.main([]) == 1
    assert config_path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [config_path]


def test_upgrade_applies_all_steps_for_skipped_versions(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    original = b"config_version = 2\n[run]\nlibrary_folder = 'shows'\n"
    path.write_bytes(original)
    monkeypatch.setattr(bootstrap, "CONFIG_VERSION", 4)
    monkeypatch.setattr(config_service, "CONFIG_VERSION", 4)
    monkeypatch.setattr(cli, "user_config_path", lambda: path)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        cli, "SQLiteEtreeDB", lambda path: pytest.fail("Setup opened SQLite")
    )

    def to_three(config_path, data):
        assert config_path == path
        assert data["config_version"] == 2
        data["preferences"] = {"segue_string": "~>"}

    def to_four(config_path, data):
        assert data["config_version"] == 3
        assert data["preferences"]["segue_string"] == "~>"
        data["preferences"]["write_date"] = True

    monkeypatch.setattr(bootstrap, "CONFIG_UPGRADES", {2: to_three, 3: to_four})
    assert cli.main([]) == 0
    upgraded = load_app_config(path, user_config=True)
    assert upgraded.raw["config_version"] == 4
    assert upgraded.preferences.write_date
    assert upgraded.preferences.segue_string == "~>"
    assert path.with_name("config.toml.v2.bak").read_bytes() == original
    assert not path.with_name("config.toml.v3.bak").exists()


def test_missing_upgrade_step_leaves_original_alone(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    original = b"config_version = 1\n"
    path.write_bytes(original)
    monkeypatch.setattr(bootstrap, "CONFIG_VERSION", 3)
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("Setup prompted"))
    with pytest.raises(
        ValueError, match="No configuration upgrade available from 2 to 3"
    ):
        bootstrap.upgrade_user_config(path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_advanced_tagging_prompts_use_custom_album_labels(monkeypatch, capsys):
    config = load_app_config(SHIPPED_CONFIG)
    answers = iter(
        ["2", "", "", "", "no", "3", "yes", ""]
        + [""] * 12
        + ["Board", "Audience", "MAT", "", "~>", "yes", "yes", "yes"]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    _ask_tagging_preferences(config)

    assert "73-10-29 St. Louis, MO MAT" in capsys.readouterr().out
    assert config.preferences.soundboard_abbrev == "Board"
    assert config.preferences.aud_abbrev == "Audience"
    assert config.preferences.segue_string == "~>"
    assert config.preferences.enable_filename_fallback is True
    assert config.preferences.write_date and config.preferences.write_date_parts
    assert not config.album_tag.include_shnid
    assert not config.album_tag.include_bitrate


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "1974-06-28",
            {"date": "1974-06-28", "year": "1974", "month": "06", "day": "28"},
        ),
        ("1974-06-xx", {"date": "1974-06", "year": "1974", "month": "06"}),
        ("1974", {"date": "1974", "year": "1974"}),
        (
            "10/29/65",
            {"date": "1965-10-29", "year": "1965", "month": "10", "day": "29"},
        ),
        ("1974-02-30", {}),
    ],
)
def test_performance_date_tags(raw, expected):
    assert performance_date_tags(raw, True, True) == expected


def test_worker_writes_performance_date_and_preserves_unknown_components(monkeypatch):
    class Audio(dict):
        def save(self):
            self.saved = True

    audio = Audio(day="28", description="old")
    monkeypatch.setattr("services.tagging.FLAC", lambda path: audio)
    args = (
        "a.flac",
        "a.flac",
        None,
        False,
        True,
        "Album",
        None,
        "Artist",
        "source",
        "01",
        "1",
        "Title",
    )
    assert tag_file_worker(args, performance_date_tags("1974-06", True, True))[1]
    assert audio.saved
    assert (audio["date"], audio["year"], audio["month"], audio["day"]) == (
        "1974-06",
        "1974",
        "06",
        "28",
    )
    assert "description" not in audio
