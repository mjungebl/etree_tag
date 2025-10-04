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
class AppConfig:
    preferences: PreferencesConfig
    album_tag: AlbumTagConfig
    cover: CoverConfig
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

    supportfiles = SupportFilesConfig(files=dict(data.get("supportfiles", {})))

    return AppConfig(
        preferences=pref_defaults,
        album_tag=album_defaults,
        cover=cover_defaults,
        supportfiles=supportfiles,
        raw=data,
    )
