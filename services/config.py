from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import tomllib

CONFIG_VERSION = 1
SHIPPED_CONFIG = Path(__file__).resolve().parents[1] / "config.toml"
LIBRARY_LOG_PATH = Path("tagger_logs") / "tag_log.log"


@dataclass
class RunConfig:
    library_folder: str = ""
    scan_subfolders: bool = True
    database: str = ""
    log_file: str = ""
    clear_tags: bool = False


@dataclass
class CoverConfig:
    clear_existing_artwork: bool = False
    retain_existing_artwork: bool = True
    artwork_folders: Dict[str, List[str]] = field(default_factory=dict)
    default_images: Dict[str, str] = field(default_factory=dict)


@dataclass
class PreferencesConfig:
    year_format: str = "YYYY"
    segue_string: str = "->"
    soundboard_abbrev: str = "SBD"
    aud_abbrev: str = "AUD"
    matrix_abbrev: Optional[str] = None
    ultramatrix_abbrev: Optional[str] = None
    verbose_logging: bool = False
    enable_filename_fallback: bool = False


@dataclass
class AlbumTagConfig:
    include_bitrate: bool = True
    include_bitrate_not16_only: bool = True
    include_shnid: bool = True
    include_venue: bool = False
    include_city: bool = True
    order: List[str] = field(
        default_factory=lambda: [
            "show_date",
            "city",
            "venue",
            "recording_type",
            "shnid",
            "bitrate",
        ]
    )
    prefix: List[str] = field(default_factory=list)
    suffix: List[str] = field(default_factory=list)


@dataclass
class SupportFilesConfig:
    files: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.files.get(key, default)


@dataclass
class RecordingFolderConfig:
    standardize_artist_abbrev: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class AppConfig:
    preferences: PreferencesConfig
    album_tag: AlbumTagConfig
    cover: CoverConfig
    recording_folder: RecordingFolderConfig
    supportfiles: SupportFilesConfig
    raw: Dict[str, object] = field(default_factory=dict)
    run: RunConfig = field(default_factory=RunConfig)

    def to_mapping(self) -> Dict[str, object]:
        """Return a dict compatible with legacy code expecting nested mappings."""
        return {
            "preferences": vars(self.preferences),
            "album_tag": {
                **vars(self.album_tag),
                # ensure tuple compatibility for TitleBuilder legacy usage
                "order": list(self.album_tag.order),
                "prefix": list(self.album_tag.prefix),
                "suffix": list(self.album_tag.suffix),
            },
            "cover": {
                "clear_existing_artwork": self.cover.clear_existing_artwork,
                "retain_existing_artwork": self.cover.retain_existing_artwork,
                "artwork_folders": self.cover.artwork_folders,
                "default_images": self.cover.default_images,
            },
            "recording_folder": {
                "standardize_artist_abbrev": self.recording_folder.standardize_artist_abbrev,
            },
            "supportfiles": self.supportfiles.files,
        }


def _read_config(path: Path, require_version: bool) -> dict:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    version = data.get("config_version")
    if (version is not None or require_version) and (
        type(version) is not int or version != CONFIG_VERSION
    ):
        raise ValueError(
            f"Unsupported config_version {version!r}. Expected {CONFIG_VERSION}."
        )
    return data


def _merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            value = _merge(result[key], value)
        result[key] = value
    return result


def _resolve_paths(data: dict, directory: Path) -> None:
    def resolve(value):
        if isinstance(value, str) and value:
            path = Path(value).expanduser()
            return str(directory / path) if not path.is_absolute() else str(path)
        return value

    for section, keys in (
        ("run", ("library_folder", "database", "log_file")),
        ("cover", ("default_images", "artwork_folders")),
        ("supportfiles", ()),
    ):
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"[{section}] must be a table.")
        for key in keys or tuple(values):
            if key not in values:
                continue
            value = values[key]
            if isinstance(value, dict):
                values[key] = {
                    name: [resolve(path) for path in item] if isinstance(item, list)
                    else resolve(item)
                    for name, item in value.items()
                }
            else:
                values[key] = resolve(value)


def _validate_config(data: dict) -> None:
    for section, model in (
        ("run", RunConfig()),
        ("preferences", PreferencesConfig()),
        ("album_tag", AlbumTagConfig()),
        ("cover", CoverConfig()),
        ("supportfiles", {}),
        ("recording_folder", RecordingFolderConfig()),
    ):
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"[{section}] must be a table.")
        fields = model if isinstance(model, dict) else vars(model)
        for key, expected in fields.items():
            if key not in values:
                continue
            value = values[key]
            kind = str if expected is None else type(expected)
            if type(value) is not kind or (
                kind is list and any(not isinstance(item, str) for item in value)
            ):
                label = "list of strings" if kind is list else kind.__name__
                raise ValueError(f"{section}.{key} must be a {label}.")
    if data.get("preferences", {}).get("year_format", "YYYY").upper() not in {"YY", "YYYY"}:
        raise ValueError("preferences.year_format must be YY or YYYY.")
    album = data.get("album_tag", {})
    if "prefix" in album or "suffix" in album:
        if len(album.get("order", AlbumTagConfig().order)) != len(album.get("prefix", [])) or (
            len(album.get("prefix", [])) != len(album.get("suffix", []))
        ):
            raise ValueError("album_tag.order, prefix and suffix must have the same length.")
    if set(album.get("order", [])) - set(AlbumTagConfig().order):
        raise ValueError("album_tag.order contains an unsupported component.")
    cover = data.get("cover", {})
    for paths in cover.get("artwork_folders", {}).values():
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise ValueError("cover.artwork_folders must map artists to lists of paths.")
    if any(not isinstance(path, str) for path in cover.get("default_images", {}).values()):
        raise ValueError("cover.default_images must map artists to paths.")
    if any(not isinstance(path, str) for path in data.get("supportfiles", {}).values()):
        raise ValueError("supportfiles must map tool names to paths.")


def load_app_config(path: str | Path, *, user_config: bool = False) -> AppConfig:
    path = Path(path).expanduser().absolute()
    data = _read_config(path, require_version=user_config)
    if user_config or "config_version" in data:
        baseline = _read_config(SHIPPED_CONFIG, require_version=False)
        _resolve_paths(baseline, SHIPPED_CONFIG.parent)
        _resolve_paths(data, path.parent)
        data = _merge(baseline, data)
    _validate_config(data)

    pref_defaults = PreferencesConfig()
    for key, value in (data.get("preferences") or {}).items():
        setattr(pref_defaults, key, value)

    album_defaults = AlbumTagConfig()
    for key, value in (data.get("album_tag") or {}).items():
        setattr(album_defaults, key, value)
    album_defaults.order = list(album_defaults.order)
    album_defaults.prefix = list(album_defaults.prefix)
    album_defaults.suffix = list(album_defaults.suffix)

    cover_defaults = CoverConfig()
    cover_section = data.get("cover") or {}
    cover_defaults.clear_existing_artwork = cover_section.get(
        "clear_existing_artwork", cover_defaults.clear_existing_artwork
    )
    cover_defaults.retain_existing_artwork = cover_section.get(
        "retain_existing_artwork", cover_defaults.retain_existing_artwork
    )
    cover_defaults.artwork_folders = dict(cover_section.get("artwork_folders", {}))
    cover_defaults.default_images = dict(cover_section.get("default_images", {}))

    recording_section = data.get("recording_folder") or {}
    alias_section = recording_section.get("standardize_artist_abbrev") or {}

    alias_map: Dict[str, List[str]] = {}
    for key, value in alias_section.items():
        if value is None:
            continue
        if isinstance(value, str):
            entries = [value]
        else:
            try:
                entries = list(value)
            except TypeError:
                entries = [value]
        cleaned = []
        for entry in entries:
            if entry is None:
                continue
            entry_str = str(entry).strip()
            if entry_str:
                cleaned.append(entry_str)
        if cleaned:
            alias_map[str(key).lower()] = cleaned

    recording_folder = RecordingFolderConfig(
        standardize_artist_abbrev=alias_map,
    )

    supportfiles = SupportFilesConfig(files=dict(data.get("supportfiles", {})))

    return AppConfig(
        preferences=pref_defaults,
        album_tag=album_defaults,
        cover=cover_defaults,
        recording_folder=recording_folder,
        supportfiles=supportfiles,
        raw=data,
        run=RunConfig(**{
            key: value for key, value in data.get("run", {}).items()
            if key in vars(RunConfig())
        }),
    )
