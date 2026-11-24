import logging
import re
from datetime import date, datetime
from typing import Optional, Tuple

from mutagen.flac import FLAC

from services.artwork import apply_artwork_to_audio, set_audio_artwork

logger = logging.getLogger(__name__)


WorkerResult = Tuple[str, bool, Optional[str]]


def performance_date_tags(
    raw: str | None, write_date: bool, write_parts: bool
) -> dict[str, str]:
    """Build tags from the known components of the catalog date."""
    if not raw or not (write_date or write_parts):
        return {}
    raw = raw.strip()
    match = re.fullmatch(
        r"(\d{4})(?:[-./](\d{1,2}|[xX]{1,2})(?:[-./](\d{1,2}|[xX]{1,2}))?)?",
        raw,
    )
    if match:
        year, month, day = [
            int(part) if part and part.isdigit() else None for part in match.groups()
        ]
        try:
            date(year, 1 if month is None else month, 1 if day is None else day)
        except ValueError:
            return {}
        if day is not None and month is None:
            return {}
    else:
        if re.fullmatch(r"\d{1,2}[-./]\d{1,2}[-./]\d{2}", raw):
            short_year = int(raw[-2:])
            year = short_year + (
                2000 if short_year <= datetime.now().year % 100 else 1900
            )
            raw = f"{raw[:-2]}{year}"
        for fmt in (
            "%m-%d-%Y",
            "%m/%d/%Y",
            "%m.%d.%Y",
        ):
            try:
                parsed = datetime.strptime(raw, fmt)
            except ValueError:
                continue
            year, month, day = parsed.year, parsed.month, parsed.day
            break
        else:
            return {}

    parts = {"year": f"{year:04d}"}
    if month is not None:
        parts["month"] = f"{month:02d}"
    if day is not None:
        parts["day"] = f"{day:02d}"
    tags = dict(parts) if write_parts else {}
    if write_date:
        tags["date"] = "-".join(parts.values())
    return tags


def tag_file_worker(args, date_tags: dict[str, str] | None = None) -> WorkerResult:
    """Worker function to add artwork and metadata to a single FLAC file."""
    file_path, file_name = args[:2]
    try:
        audio = FLAC(file_path)
        prepare_file_tags(audio, args, date_tags)
        audio.save()
        return (file_name, True, None)
    except Exception as exc:  # pragma: no cover - worker failure path
        logger.error("Error tagging file %s: %s", file_name, exc)
        return (file_name, False, str(exc))


def prepare_file_tags(audio, args, date_tags, *, image_data: bytes | None = None):
    (
        file_path,
        file_name,
        artwork_path,
        clear_existing_artwork,
        clear_existing_tags,
        album,
        genretag,
        artist,
        source,
        tracknum,
        disc,
        title,
    ) = args

    if image_data is None:
        apply_artwork_to_audio(audio, file_name, artwork_path, clear_existing_artwork)
    else:
        set_audio_artwork(audio, file_name, artwork_path, image_data, clear_existing_artwork)

    if clear_existing_tags:
        for key in list(audio.keys()):
            if key.lower() == "metadata_block_picture" or (
                date_tags is not None
                and key.lower() in {"date", "year", "month", "day"}
            ):
                continue
            del audio[key]
        logger.debug("Cleared tags from file: %s", file_name)

    audio["album"] = album
    audio["artist"] = artist
    audio["albumartist"] = artist
    if "album artist" in audio:
        del audio["album artist"]
    audio["comment"] = source
    if genretag:
        audio["genre"] = genretag
    for key, value in (date_tags or {}).items():
        audio[key] = value

    if title:
        audio["title"] = title
        if disc:
            audio["discnumber"] = disc
        if tracknum:
            audio["tracknumber"] = tracknum
    else:
        logger.warning("No matching track data found for %s", file_path)


def tag_artwork_worker(args) -> WorkerResult:
    """Worker function to add artwork to a single FLAC file."""
    file_path, file_name, artwork_path, clear_existing = args
    try:
        audio = FLAC(file_path)
        changed, error = apply_artwork_to_audio(
            audio, file_name, artwork_path, clear_existing
        )
        if error:
            return (file_name, False, error)
        if changed:
            audio.save()
        return (file_name, True, None)
    except Exception as exc:  # pragma: no cover - worker failure path
        logger.error("Error tagging file %s: %s", file_name, exc)
        return (file_name, False, str(exc))
