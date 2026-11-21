"""Interactive setup for the user's persistent tagging preferences."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from services.config import (
    CONFIG_VERSION,
    LIBRARY_LOG_PATH,
    SHIPPED_CONFIG,
    load_app_config,
)


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
    verbose = _yes_no(
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
    print("\nTag formatting uses the shipped defaults.")

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
        f"verbose_logging = {str(verbose).lower()}",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=path.parent, mode="w", encoding="utf-8", delete=False
    ) as file:
        temporary = Path(file.name)
        try:
            file.write("\n".join(content))
            file.close()
            load_app_config(temporary, user_config=True)
            # Publish a complete file without replacing one written by another setup.
            os.link(temporary, path)
        finally:
            file.close()
            temporary.unlink()
    print(f"Saved preferences to {path.resolve()}")
    print("Edit that .toml file in a text editor to change your preferences.")
    print("Run Etree Tag (python cli.py) again to use these settings.")
