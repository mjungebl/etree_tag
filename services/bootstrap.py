"""Interactive setup for the user's persistent tagging preferences."""

import json
import os
import tomllib
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace

from services.config import (
    CONFIG_VERSION,
    LIBRARY_LOG_PATH,
    SHIPPED_CONFIG,
    AppConfig,
    build_app_config,
    load_app_config,
)
from tagger_utils import TitleBuilder


def user_config_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
        return root / "EtreeTag" / "config.toml"
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "etree-tag" / "config.toml"


def _prompt(label: str, default: str, *, current: bool = False) -> str:
    display = f"currently {default}" if current else default or "required"
    return input(f"{label} [{display}]: ").strip() or default


def _path(
    label: str, default: str, *, kind: str = "output", current: bool = False
) -> str:
    while True:
        answer = _prompt(label, default, current=current).strip('"')
        if answer:
            path = Path(answer).expanduser().resolve()
            if (
                (kind == "folder" and path.is_dir())
                or (kind == "file" and path.is_file())
                or (kind == "catalog" and path.parent.is_dir() and not path.is_dir())
                or (kind == "output" and not path.is_dir())
            ):
                return str(path)
        print(f"Enter a valid {kind} path.")


def _yes_no(label: str, default: bool) -> bool:
    while True:
        answer = _prompt(label, "yes" if default else "no").lower()
        if answer in {"yes", "y", "no", "n"}:
            return answer in {"yes", "y"}
        print("Enter yes or no.")


def _choice(label: str, default: str, choices: tuple[str, ...]) -> str:
    while True:
        answer = _prompt(label, default)
        if answer in choices:
            return answer
        print(f"Choose one of {', '.join(choices)}.")


def _show_album_example(config: AppConfig) -> None:
    recording = SimpleNamespace(
        date="1973-10-29", city="St. Louis, MO", etreevenue="Kiel Auditorium", id=131409
    )
    info = SimpleNamespace(bits_per_sample=24, sample_rate=96000)
    folder = SimpleNamespace(
        recordingtype="MTX",
        musicfiles=[SimpleNamespace(audio=SimpleNamespace(info=info))],
    )
    print(
        f"Example album name: {TitleBuilder(recording, folder, config.to_mapping()).generate_title()}"
    )


def _ask_tagging_preferences(config: AppConfig) -> None:
    prefs, album = config.preferences, config.album_tag
    print("\nALBUM TAG\nChoose what appears in the FLAC ALBUM tag.")
    prefs.year_format = "Y" * int(
        _choice(
            "Show year with 4 digits or 2 digits?",
            str(len(prefs.year_format)),
            ("4", "2"),
        )
    )
    album.include_city = _yes_no(
        "Include the city in the album name?", album.include_city
    )
    album.include_venue = _yes_no(
        "Include the venue in the album name?", album.include_venue
    )
    album.include_recording_type = _yes_no(
        "Include the recording type, such as SBD or AUD?", album.include_recording_type
    )
    album.include_shnid = _yes_no(
        "Include the Etree source ID (SHNID) in the album name?", album.include_shnid
    )
    print(
        "Show bit depth and sample rate in the album name?\n"
        "  1. Only for recordings above 16-bit\n"
        "  2. For all recordings\n"
        "  3. Never"
    )
    resolution_default = (
        "3"
        if not album.include_bitrate
        else "1"
        if album.include_bitrate_not16_only
        else "2"
    )
    resolution = _choice("Choose", resolution_default, ("1", "2", "3"))
    album.include_bitrate = resolution != "3"
    album.include_bitrate_not16_only = resolution == "1"
    _show_album_example(config)

    if _yes_no("Customize field order, separators, or recording-type labels?", False):
        existing = dict(zip(album.order, zip(album.prefix, album.suffix)))
        while True:
            order = _prompt(
                "Album field order (comma-separated)", ", ".join(album.order)
            )
            fields = [field.strip() for field in order.split(",")]
            if len(fields) == len(existing) and set(fields) == set(existing):
                break
            print("List each existing field exactly once.")
        album.order = fields
        album.prefix = []
        album.suffix = []
        print(
            'For prefixes and suffixes, Enter keeps the current text. Type "" to clear it.'
        )
        for field in fields:
            for label, default, target in (
                ("Prefix", existing[field][0], album.prefix),
                ("Suffix", existing[field][1], album.suffix),
            ):
                value = input(f"{label} for {field} [{json.dumps(default)}]: ")
                target.append(
                    default if value == "" else "" if value == '""' else value
                )
        prefs.soundboard_abbrev = _prompt(
            "Soundboard (SBD) label", prefs.soundboard_abbrev
        )
        prefs.aud_abbrev = _prompt("Audience (AUD) label", prefs.aud_abbrev)
        prefs.matrix_abbrev = _prompt(
            "Matrix (MTX) label", prefs.matrix_abbrev or "MTX"
        )
        prefs.ultramatrix_abbrev = _prompt(
            "Ultramatrix label", prefs.ultramatrix_abbrev or "Ultramatrix"
        )
        _show_album_example(config)

    print("\nTRACK TITLES")
    prefs.segue_string = _prompt(
        "What marker should follow a song that segues into the next?",
        prefs.segue_string,
    )
    print(f"  Example: China Cat Sunflower {prefs.segue_string}")
    prefs.enable_filename_fallback = _yes_no(
        "Allow track details to be inferred from filenames when the info file can't supply them?",
        prefs.enable_filename_fallback,
    )

    print("\nPERFORMANCE DATE TAGS")
    prefs.write_date = _yes_no(
        "Write the show date to each FLAC's DATE tag, such as 1973-10-29?",
        prefs.write_date,
    )
    if prefs.write_date:
        print("  Some players only read DATE. Only known date components are written.")
        prefs.write_date_parts = _yes_no(
            "Also write separate YEAR, MONTH, and DAY tags?", prefs.write_date_parts
        )


def _toml_value(value) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, dict):
        fields = (
            f"{_toml_value(key)} = {_toml_value(item)}" for key, item in value.items()
        )
        return "{ " + ", ".join(fields) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(map(_toml_value, value)) + "]"
    return str(value)


def _settings_lines(data: dict) -> list[str]:
    lines = [f"config_version = {data['config_version']}"]
    for key, value in data.items():
        if key != "config_version" and not isinstance(value, dict):
            lines.append(f"{_toml_value(key)} = {_toml_value(value)}")
    for section, settings in data.items():
        if isinstance(settings, dict):
            lines.extend(("", f"[{_toml_value(section)}]"))
            lines.extend(
                f"{_toml_value(key)} = {_toml_value(value)}"
                for key, value in settings.items()
            )
    return lines


def _save_config(
    path: Path, content: list[str], previous: tuple[int, bytes] | None = None
) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=path.parent, mode="w", encoding="utf-8", delete=False
    ) as file:
        temporary = Path(file.name)
        try:
            file.write("\n".join([*content, ""]))
            file.close()
            load_app_config(temporary, user_config=True)
            if previous is None:
                # Publish without replacing a file written by another setup.
                os.link(temporary, path)
                return None
            version, original = previous
            if path.read_bytes() != original:
                raise ValueError("Configuration changed during setup. Run setup again.")
            backup_name = f"{path.name}.v{version}.bak"
            backup = path.with_name(backup_name)
            index = 2
            while True:
                try:
                    os.link(path, backup)
                except FileExistsError:
                    backup = path.with_name(f"{backup_name}.{index}")
                    index += 1
                else:
                    break
            os.replace(temporary, path)
            return backup
        finally:
            file.close()
            temporary.unlink(missing_ok=True)


def _upgrade_v1_to_v2(path: Path, data: dict) -> None:
    config = build_app_config(path, data, inherit_defaults=True)
    if "segue_string" not in data.get("preferences", {}):
        config.preferences.segue_string = "->"
    print(
        "This version adds choices for album tags, track titles, and performance dates."
    )
    _ask_tagging_preferences(config)
    for section in ("preferences", "album_tag"):
        settings = data.setdefault(section, {})
        settings.update(
            (key, value)
            for key, value in asdict(getattr(config, section)).items()
            if value is not None
        )


# Register one step per starting version. Each step changes the data in memory.
CONFIG_UPGRADES = {1: _upgrade_v1_to_v2}


def upgrade_user_config(path: Path) -> None:
    original = path.read_bytes()
    data = tomllib.loads(original.decode("utf-8"))
    source = data.get("config_version")
    if type(source) is not int or not 1 <= source < CONFIG_VERSION:
        raise ValueError("Expected an older supported configuration.")
    versions = range(source, CONFIG_VERSION)
    for version in versions:
        if version not in CONFIG_UPGRADES:
            raise ValueError(
                f"No configuration upgrade available from {version} to {version + 1}."
            )

    print(f"CONFIGURATION UPDATE REQUIRED")
    print(f"Etree Tag configuration upgrade from version {source} to {CONFIG_VERSION}.")
    print()
    print(f"Current config (version {source}): {path.resolve()}")
    print(f"Updated config (version {CONFIG_VERSION}): same path")
    print(
        "Press Enter to keep the displayed values. Your other preferences carry forward."
    )
    print("Setup will back up your current config before saving the update.")
    for version in versions:
        print(f"\nConfiguration step {version} to {version + 1}")
        CONFIG_UPGRADES[version](path, data)
        data["config_version"] = version + 1

    backup = _save_config(path, _settings_lines(data), (source, original))
    print(f"\nUpdated preferences at {path.resolve()}")
    print(f"Previous TOML backed up at {backup.resolve()}")
    print("Run Etree Tag (python cli.py) again to use these settings.")


def create_user_config(path: Path, database: str, log_file: str | None) -> None:
    defaults = load_app_config(SHIPPED_CONFIG)
    print("Etree Tag first-run setup. Press Enter to accept the displayed default.")
    library = _path("Show or library folder", "", kind="folder")
    scan = _yes_no(
        "Treat each direct subfolder as a show? Choose no if the above folder is a single show.",
        True,
    )
    database = _path("SQLite catalog", database, kind="catalog", current=True)
    log_file = _path(
        "Base log file (each run adds a timestamp)",
        log_file or str(Path(library) / LIBRARY_LOG_PATH),
    )
    defaults.preferences.verbose_logging = _yes_no(
        "Enable verbose diagnostic logging", defaults.preferences.verbose_logging
    )
    clear_tags = _yes_no("Clear existing FLAC tags before writing", False)
    replace_art = _yes_no(
        "Replace existing artwork", defaults.cover.clear_existing_artwork
    )
    retain_art = defaults.cover.retain_existing_artwork
    if replace_art:
        retain_art = _yes_no("Back up replaced folder artwork", retain_art)

    fallback_images = {}
    for artist, image in defaults.cover.default_images.items():
        fallback_images[artist] = _path(
            f"Fallback image for {artist}",
            str(SHIPPED_CONFIG.parent / image),
            kind="file",
            current=True,
        )
    artwork_folders = {}
    for artist, folders in defaults.cover.artwork_folders.items():
        artwork_folders[artist] = [
            _path(
                f"Artwork collection {index} for {artist}",
                str(SHIPPED_CONFIG.parent / folder),
                kind="folder",
                current=True,
            )
            for index, folder in enumerate(folders, start=1)
        ]
    _ask_tagging_preferences(defaults)

    def string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")

    content = [
        "# Etree Tag user preferences. Omitted settings use the shipped defaults.",
        f"config_version = {CONFIG_VERSION}",
        "",
        "[run]",
        f"library_folder = {string(library)}",
        "# true: tag each immediate subfolder. false: tag library_folder itself.",
        "# Applies on future runs that use the saved folder.",
        f"scan_subfolders = {str(scan).lower()}",
        f"database = {string(database)}",
        f"log_file = {string(log_file)}",
        f"clear_tags = {str(clear_tags).lower()}",
        "",
        "[preferences]",
        *(
            f"{key} = {json.dumps(value, ensure_ascii=False)}"
            for key, value in asdict(defaults.preferences).items()
            if value is not None
        ),
        "",
        "[album_tag]",
        *(
            f"{key} = {json.dumps(value, ensure_ascii=False)}"
            for key, value in asdict(defaults.album_tag).items()
        ),
        "",
        "[cover]",
        f"clear_existing_artwork = {str(replace_art).lower()}",
        f"retain_existing_artwork = {str(retain_art).lower()}",
        "",
        "[cover.default_images]",
        *(
            f"{string(artist)} = {string(image)}"
            for artist, image in fallback_images.items()
        ),
        "",
        "[cover.artwork_folders]",
        *(
            f"{string(artist)} = [{', '.join(map(string, folders))}]"
            for artist, folders in artwork_folders.items()
        ),
        "",
    ]
    _save_config(path, content)
    print(f"\nSETUP COMPLETE\nSaved preferences to {path.resolve()}")
    print("Edit that .toml file in a text editor to change your preferences.")
    print("Run Etree Tag (python cli.py) again to use these settings.")
