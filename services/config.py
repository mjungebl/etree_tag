from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import tomllib


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


def load_app_config(path: str | Path) -> AppConfig:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)

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
    )
