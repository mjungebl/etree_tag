import logging
from typing import Optional, Tuple

from mutagen.flac import FLAC

from services.artwork import apply_artwork_to_audio


WorkerResult = Tuple[str, bool, Optional[str]]


def tag_file_worker(args) -> WorkerResult:
    """Worker function to add artwork and metadata to a single FLAC file."""
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

    try:
        audio = FLAC(file_path)
        apply_artwork_to_audio(audio, file_name, artwork_path, clear_existing_artwork)

        if clear_existing_tags:
            for key in list(audio.keys()):
                if key.lower() == "metadata_block_picture":
                    continue
                del audio[key]
            logging.info("Cleared tags from file: %s", file_name)

        audio["album"] = album
        audio["artist"] = artist
        audio["albumartist"] = artist
        if "album artist" in audio:
            del audio["album artist"]
        audio["comment"] = source
        if genretag:
            audio["genre"] = genretag

        if title:
            audio["title"] = title
            if disc:
                audio["discnumber"] = disc
            if tracknum:
                audio["tracknumber"] = tracknum
        else:
            logging.error(
                "Error tagging song details %s: No matching track data found in database",
                file_path,
            )
        audio.save()
        return (file_name, True, None)
    except Exception as exc:  # pragma: no cover - worker failure path
        logging.error("Error tagging file %s: %s", file_name, exc)
        return (file_name, False, str(exc))


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
        logging.error("Error tagging file %s: %s", file_name, exc)
        return (file_name, False, str(exc))
