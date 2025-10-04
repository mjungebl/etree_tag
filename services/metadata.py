import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from mutagen.flac import FLAC

from InfoFileTagger_class import FlacInfoFileTagger
from recordingfiles import RecordingFolder
from services.exceptions import MetadataImportError, PersistenceError
from services.persistence import TrackMetadataRepository

logger = logging.getLogger(__name__)

TrackMapping = Dict[str, Tuple[int, str, str]]


class MetadataImporter:
    """Handle populating track metadata from local sources."""

    def __init__(
        self,
        info_tagger: Optional[FlacInfoFileTagger] = None,
        repository: Optional[TrackMetadataRepository] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        if info_tagger is None:
            info_logger = logging.getLogger("FlacInfoFileTagger")
            info_tagger = FlacInfoFileTagger(
                logger=info_logger,
                also_log_to_console=False,
            )
        self.info_tagger = info_tagger
        self.repository = repository

    # Public API ---------------------------------------------------------
    def import_metadata(self, tagger) -> None:
        """Populate track metadata for the supplied ``ConcertTagger`` instance."""
        directory = tagger.folderpath.as_posix()

        try:
            tagged = self.info_tagger.tag_folder(directory, clear_song_tags=False)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            self.logger.error("Info file tagging raised an exception for %s: %s", directory, exc)
            raise MetadataImportError(f"Info file tagging failed for {directory}") from exc

        if not tagged:
            self.logger.warning(
                "Info file tagging did not succeed for %s; applying filename fallback.",
                directory,
            )
            fallback_mapping = self._derive_mapping_from_filenames(tagger)
            if not fallback_mapping:
                raise MetadataImportError(
                    f"Unable to derive track metadata from info file or filenames for {directory}"
                )
            if not self._apply_track_mapping(fallback_mapping):
                raise MetadataImportError(
                    f"Applying fallback track metadata failed for {directory}"
                )
        else:
            self.logger.info("Info file tagging reported success for %s", directory)

        tagger.folder = RecordingFolder(directory, tagger.db)
        records = tagger.build_show_inserts()
        if not records or any(rec[2] in (None, "") for rec in records):
            raise MetadataImportError(
                f"Generated records still missing track numbers for {directory}"
            )

        repository = self.repository or getattr(tagger, "repository", None)
        if repository is None:
            raise PersistenceError(
                f"No metadata repository available; cannot persist results for {directory}"
            )

        try:
            repository.overwrite_tracks(
                tagger.etreerec.id,
                records,
                md5key=tagger.etreerec.md5key,
            )
        except Exception as exc:  # pragma: no cover - DB failure path
            raise PersistenceError(
                f"Failed to persist info-file metadata for shnid {tagger.etreerec.id}: {exc}"
            ) from exc

        if hasattr(tagger.etreerec, "_tracks"):
            tagger.etreerec._tracks = None
        self.logger.info(
            "Imported track metadata for shnid %s from local files.",
            tagger.etreerec.id,
        )

    # Internal helpers ---------------------------------------------------
    @staticmethod
    def _apply_track_mapping(mapping: TrackMapping) -> bool:
        """Apply the supplied mapping directly to the FLAC files."""
        for flac_path, (disc, track, title) in mapping.items():
            try:
                audio = FLAC(flac_path)
            except Exception as exc:
                logger.error("Unable to load FLAC %s: %s", flac_path, exc)
                return False

            audio["tracknumber"] = track
            audio["discnumber"] = str(disc)
            audio["title"] = title
            try:
                audio.save()
            except Exception as exc:
                logger.error("Saving updated tags failed for %s: %s", flac_path, exc)
                return False
        return True

    def _derive_mapping_from_filenames(self, tagger) -> TrackMapping:
        """Create a best-effort mapping using FLAC filenames when parsing fails."""
        files = sorted(tagger.folder.musicfiles, key=lambda mf: mf.name)
        mapping: TrackMapping = {}
        disc = 1
        seq = 1
        pattern = re.compile(
            r"^(?:d(?P<disc>\d+)[_-]?)?(?:t(?P<ttrack>\d+)[_-]?)?(?P<num>\d+)?[\s._-]*(?P<title>.*)$",
            re.IGNORECASE,
        )

        for music_file in files:
            stem = Path(music_file.name).stem
            match = pattern.match(stem)
            if match:
                disc_str = match.group("disc")
                ttrack = match.group("ttrack")
                num = match.group("num")
                raw_title = match.group("title")

                disc_val = int(disc_str) if disc_str else disc
                if ttrack:
                    track_val = int(ttrack)
                elif num:
                    if len(num) > 2:
                        disc_val = int(num[0])
                        track_val = int(num[1:])
                    else:
                        track_val = int(num)
                else:
                    track_val = seq

                title = raw_title or stem
            else:
                disc_val = disc
                track_val = seq
                title = stem

            title_clean = self.info_tagger.clean_track_name(title.strip())
            mapping[music_file.path] = (disc_val, f"{track_val:02d}", title_clean)

            if track_val == 1 and seq != 1:
                disc = disc_val
            seq += 1

        return mapping

