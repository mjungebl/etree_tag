import os
import logging
from typing import Optional, Tuple

from mutagen.flac import FLAC, Picture


def guess_artwork_mime_type(artwork_path: str) -> str:
    """Return the mime type for the artwork based on its file extension."""
    ext = os.path.splitext(artwork_path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def apply_artwork_to_audio(
    audio: FLAC,
    file_name: str,
    artwork_path: Optional[str],
    clear_existing: bool,
) -> Tuple[bool, Optional[str]]:
    """Attach artwork to a FLAC audio object if possible."""
    if not artwork_path:
        logging.info("No artwork file found to tag.")
        return False, None

    try:
        with open(artwork_path, "rb") as f:
            image_data = f.read()
    except Exception as exc:
        logging.error("Error reading artwork file %s: %s", artwork_path, exc)
        return False, str(exc)

    if clear_existing and audio.pictures:
        audio.clear_pictures()
        logging.info("Cleared artwork from file: %s", file_name)

    if audio.pictures:
        logging.info("Artwork already exists in file: %s", file_name)
        return False, None

    picture = Picture()
    picture.type = 3  # Cover (front)
    picture.mime = guess_artwork_mime_type(artwork_path)
    picture.data = image_data
    audio.add_picture(picture)
    logging.info("Added artwork to file: %s", file_name)
    return True, None
