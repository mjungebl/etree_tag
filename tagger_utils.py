# from typing import Mapping, Any, Optional
# import logging

# class TitleBuilder:
#     # ... your __init__ with self.etreerec, self.folder, config, etc.

# Calling it:
# tb = TitleBuilder(etreerec, folder, config)
# title = tb.generate_title()  # your method from earlier; switch it to use self.config

from __future__ import annotations
from typing import Any, Callable, List, Optional, Mapping, Sequence, Tuple
import logging
from datetime import datetime
from pathlib import Path
import re
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


def extract_year(date_str):
    # Remove any leading/trailing whitespace.
    date_str = date_str.strip()

    # First, try to parse the string as a valid ISO date (YYYY-MM-DD).
    try:
        valid_date = datetime.strptime(date_str, "%Y-%m-%d")
        return valid_date.year
    except ValueError:
        # If it fails, continue with more flexible parsing.
        pass

    # Look for any four digit year in the string.
    match = re.search(r"(\d{4})", date_str)
    if match:
        return int(match.group(1))

    # Look for a two-digit year pattern at the end of the string.
    match = re.search(r"(\d{2})$", date_str)
    if match:
        two_digit = int(match.group(1))
        # Use the last two digits of the current year (e.g., "25" for 2025).
        current_threshold = int(str(datetime.now().year)[-2:])
        if two_digit <= current_threshold:
            return 2000 + two_digit
        else:
            return 1900 + two_digit

    # If no valid year is found, return None.
    return None


class TitleBuilder:
    """
    Minimal state holder for title generation.

    Parameters
    ----------
    etreerec : object
        Must expose: .date (str), .city (str|None), .etreevenue (str|None), .id (str|int).
    folder : object
        Must expose: .recordingtype (str|None), .musicfiles (Sequence with [0].audio.info.{bits_per_sample,sample_rate}).
    config : Mapping[str, Any]
        Dict-like with sections: 'preferences' and 'album_tag'.
    logger : logging.Logger, optional
        If omitted, a module logger is used.
    """

    def __init__(
        self,
        etreerec: Any,
        folder: Any,
        config: Mapping[str, Any],
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.etreerec = etreerec
        self.folder = folder
        self.config: dict[str, Any] = dict(config)  # shallow copy of top level
        self.log = logger or logging.getLogger(__name__)

        # --- light validation ---
        if "preferences" not in self.config or "album_tag" not in self.config:
            raise ValueError(
                "config must contain 'preferences' and 'album_tag' sections"
            )

        # Make sure order/prefix/suffix are mutable copies if present.
        # This avoids mutating caller state.
        album_tag = dict(self.config.get("album_tag") or {})
        for key in ("order", "prefix", "suffix"):
            if key in album_tag and album_tag[key] is not None:
                album_tag[key] = list(album_tag[key])  # copy any tuple/list
        self.config["album_tag"] = album_tag

        # Optional heads-up if bitrate logic may fail later
        if not getattr(self.folder, "musicfiles", None):
            self.log.debug(
                "TitleBuilder: folder.musicfiles is empty; bitrate may be unavailable."
            )

    @staticmethod
    def _normalize_show_date(raw: str, year_format: Optional[str]) -> str:
        """Return YYYY-MM-DD (or YY-MM-DD if year_format=='yy') when possible."""
        show_date = raw
        ty = extract_year(raw)
        if ty and raw[:4] != str(ty):
            for splitter in ("/", "-"):
                if splitter in raw:
                    parts = raw.split(splitter)
                    if len(parts) == 3:
                        show_date = f"{ty}-{parts[0]}-{parts[1]}"
                    break
        if year_format and year_format.lower() == "yy":
            show_date = show_date[2:]
        return show_date

    @staticmethod
    def _abbrev_type(
        rec_type: Optional[str], prefs: Mapping[str, Any]
    ) -> Optional[str]:
        if not rec_type:
            return rec_type
        abbr_map = {
            "sbd": prefs.get("soundboard_abbrev"),
            "aud": prefs.get("aud_abbrev"),
            "matrix": prefs.get("matrix_abbrev"),
            "ultramatrix": prefs.get("ultramatrix_abbrev"),
        }
        return abbr_map.get(rec_type.lower()) or rec_type

    @staticmethod
    def _bitrate_and_flag(
        info, include_bitrate: bool, not16_only: bool
    ) -> tuple[str, bool]:
        """Return (bitrate_str, include_bitrate_final)."""
        br = f"{info.bits_per_sample}-{str(info.sample_rate).rstrip('0')}"
        if not16_only and str(info.bits_per_sample) == "16":
            include_bitrate = False
        return br, include_bitrate

    @staticmethod
    def _prune(order, prefix, suffix, checks: Mapping[str, bool]) -> None:
        """Remove tokens from order/prefix/suffix when checks[name] is False."""
        remove = {k for k, keep in checks.items() if not keep}
        triples = [
            (o, p, s) for o, p, s in zip(order, prefix, suffix) if o not in remove
        ]
        if triples:
            order[:], prefix[:], suffix[:] = map(list, zip(*triples))
        else:
            order[:] = []
            prefix[:] = []
            suffix[:] = []

    @staticmethod
    def _build_format(order, prefix, suffix) -> Optional[str]:
        if order and len(order) == len(prefix) == len(suffix):
            return "".join(f"{p}{{{o}}}{s}" for o, p, s in zip(order, prefix, suffix))
        return None

    def generate_title(self) -> str:
        prefs = self.config["preferences"]
        tag = self.config["album_tag"]

        show_date = self._normalize_show_date(
            self.etreerec.date, prefs.get("year_format")
        )
        recording_type = self._abbrev_type(self.folder.recordingtype, prefs)

        city, venue, shnid = (
            self.etreerec.city,
            self.etreerec.etreevenue,
            self.etreerec.id,
        )
        order = (tag.get("order") or []).copy()
        prefix = (tag.get("prefix") or []).copy()
        suffix = (tag.get("suffix") or []).copy()

        info = self.folder.musicfiles[0].audio.info  # assumes at least one file
        bitrate, include_bitrate = self._bitrate_and_flag(
            info,
            tag.get("include_bitrate", True),
            tag.get("include_bitrate_not16_only", True),
        )

        checks = {
            "venue": tag.get("include_venue", True) and bool(venue),
            "city": tag.get("include_city", True) and bool(city),
            "shnid": tag.get("include_shnid", True),
            "bitrate": include_bitrate,
        }
        self._prune(order, prefix, suffix, checks)

        fmt = self._build_format(order, prefix, suffix)
        ctx = {
            "venue": venue,
            "city": city,
            "shnid": shnid,
            "bitrate": bitrate,
            "recording_type": recording_type,
            "show_date": show_date,
        }

        if fmt:
            try:
                return fmt.format_map(DefaultEmpty(ctx))
            except Exception as e:
                logging.error(
                    f"Error formatting album title. reverting to default. shnid={shnid}: {e}"
                )

        # Fallback
        album = f"{show_date} {venue} {city} "
        if recording_type:
            album += f"{recording_type} "
        if include_bitrate and self.folder.musicfiles:
            album += f"[{bitrate}] "
        return album + f"({shnid})"


class DefaultEmpty(dict):
    """format_map() helper that returns '' for missing keys."""

    def __missing__(self, key):  # type: ignore[override]
        return ""


TagWorker = Callable[
    [
        str,
        str,
        Optional[str],
        bool,
        bool,
        str,
        Optional[str],
        str,
        str,
        Optional[int],
        Optional[int],
        Optional[str],
    ],
    Tuple[str, bool, Optional[str]],
]


class FileTagger:
    """
    Orchestrates tagging a folder of music files:
      - builds the album title (via TitleBuilder)
      - handles artwork copy/retention
      - builds per-track args
      - runs multithreaded tagging with a provided worker

    Inject your single-file worker (e.g., `_tag_file_thread`) so this stays framework-agnostic.
    """

    def __init__(
        self,
        *,
        etreerec: Any,
        folder: Any,
        config: dict,
        folderpath: Path,
        artworkpath: Optional[Path],
        db_path: Optional[str],
        worker: TagWorker,
        logger: Optional[logging.Logger] = None,
        title_builder_cls: type = None,
    ) -> None:
        self.etreerec = etreerec
        self.folder = folder
        self.config = config
        self.folderpath = folderpath
        self.artworkpath = artworkpath
        self.db_path = db_path
        self.worker = worker
        self.log = logger or logging.getLogger(__name__)
        self.title_builder_cls = title_builder_cls  # pass TitleBuilder, or None to skip

    # ---- public API ---------------------------------------------------------

    def tag_all(
        self, clear_existing_tags: bool = True, num_threads: Optional[int] = None
    ) -> None:
        album = self._compute_album_title()
        print(f"{album=}")
        self.log.info(f"Tagging {album} in {self.folderpath.as_posix()}")

        if not getattr(self.etreerec, "tracks", None):
            msg = (
                f"ERROR: Unable to tag track names. No metadata found in {self.db_path} "
                f"for {self.folderpath.as_posix()}"
            )
            print(msg)
            self.log.error(msg)

        genretag = self._compute_genretag()
        clear_existing_artwork = self.config.get("cover", {}).get(
            "clear_existing_artwork", False
        )
        retain_existing_artwork = self.config.get("cover", {}).get(
            "retain_existing_artwork", True
        )

        artwork_path_str = self._handle_artwork(
            clear_existing_artwork, retain_existing_artwork
        )

        gazinta_abbrev = self.config.get("preferences", {}).get("segue_string") or ">"

        args_list = self._build_args_list(
            album=album,
            genretag=genretag,
            gazinta_abbrev=gazinta_abbrev,
            artwork_path_str=artwork_path_str,
            clear_existing_artwork=clear_existing_artwork,
            clear_existing_tags=clear_existing_tags,
        )

        self._run_threads(args_list, num_threads)

    # ---- steps --------------------------------------------------------------

    def _compute_album_title(self) -> str:
        """Prefer TitleBuilder if provided; fallback to any `self.generate_title()` on the host object."""
        if self.title_builder_cls is not None:
            tb = self.title_builder_cls(self.etreerec, self.folder, self.config)
            title = tb.generate_title()
        elif hasattr(self, "generate_title"):
            title = self.generate_title()  # type: ignore[attr-defined]
        else:
            # last-resort fallback
            title = f"{getattr(self.etreerec, 'date', '?')} {getattr(self.etreerec, 'etreevenue', '')} {getattr(self.etreerec, 'city', '')}"
        return title

    def _compute_genretag(self) -> Optional[str]:
        """Example: tag GD shows by year as 'gdYYYY'. Extend/parametrize as needed."""
        if (
            getattr(self.etreerec, "date", None)
            and getattr(self.etreerec, "artist", "") == "Grateful Dead"
        ):
            if len(self.etreerec.date) > 4:
                try:
                    # Use your existing extract_year if available; otherwise a tiny fallback
                    year = extract_year(self.etreerec.date)  # noqa: F821 (assumed present in your codebase)
                except NameError:
                    year = self._fallback_extract_year(self.etreerec.date)
                if year:
                    return f"gd{year}"
        return None

    def _handle_artwork(
        self, clear_existing_artwork: bool, retain_existing_artwork: bool
    ) -> Optional[str]:
        """
        Manage copying/retaining artwork in the target folder.
        Returns the path string to the artwork used (or None if none available).
        """
        if not self.artworkpath:
            self.log.warning("No artwork file found to tag.")
            return None

        folder_dir = self.folderpath.as_posix()
        artwork_path_str = self.artworkpath.as_posix()
        artwork_ext = os.path.splitext(artwork_path_str)[1].lower()
        artwork_formats = ["jpg", "jpeg", "png", "gif", "bmp", "webp"]

        existing_artworks = [
            os.path.join(folder_dir, f"folder.{ext}")
            for ext in artwork_formats
            if os.path.exists(os.path.join(folder_dir, f"folder.{ext}"))
        ]
        if existing_artworks:
            self.log.info(f"Existing artwork files found: {existing_artworks}")

        if existing_artworks and not clear_existing_artwork:
            self.log.info(
                f"Existing artwork found ({existing_artworks}), and replacement is disabled. Skipping copy."
            )

        # Destination: respect existing format if present, otherwise mirror new art's ext
        if existing_artworks:
            existing_ext = os.path.splitext(existing_artworks[0])[1].lower()
            dest_file = os.path.join(folder_dir, f"folder{existing_ext}")
        else:
            dest_file = os.path.join(folder_dir, f"folder{artwork_ext}")

        # Handle removal/retention of old files
        if clear_existing_artwork and existing_artworks:
            for existing in existing_artworks:
                if retain_existing_artwork:
                    backup_name = f"{existing}.old"
                    try:
                        os.rename(existing, backup_name)
                        self.log.info(f"Renamed {existing} to {backup_name}")
                    except OSError as e:
                        self.log.error(f"Failed to rename {existing}: {e}")
                else:
                    try:
                        os.remove(existing)
                        self.log.info(f"Deleted existing artwork {existing}")
                    except OSError as e:
                        self.log.error(f"Failed to delete {existing}: {e}")

        # Copy new artwork if needed
        try:
            if os.path.exists(dest_file):
                self.log.info(
                    f"{dest_file} already exists. Not replacing due to retention policy."
                )
            else:
                shutil.copy2(artwork_path_str, dest_file)
                self.log.info(f"Copied new artwork to {dest_file}.")
        except FileNotFoundError as e:
            self.log.error(
                f"Error copying artwork file {artwork_path_str} to {dest_file}: {e}"
            )
        return artwork_path_str

    def _build_args_list(
        self,
        *,
        album: str,
        genretag: Optional[str],
        gazinta_abbrev: str,
        artwork_path_str: Optional[str],
        clear_existing_artwork: bool,
        clear_existing_tags: bool,
    ) -> List[tuple]:
        args_list: List[tuple] = []

        for mf in self.folder.musicfiles:
            # Expect mf to have .path, .name, .checksum
            song_info = self.etreerec.get_track_by_checksum(mf.checksum)

            tracknum: Optional[int] = None
            disc: Optional[int] = None
            title: Optional[str] = None
            if song_info:
                title = song_info.title
                if getattr(song_info, "gazinta", False):
                    title = f"{title} {gazinta_abbrev}"
                tracknum = getattr(song_info, "tracknum", None)
                disc = getattr(song_info, "disc", None)

            args_list.append(
                (
                    mf.path,
                    mf.name,
                    artwork_path_str,
                    clear_existing_artwork,
                    clear_existing_tags,
                    album,
                    genretag,
                    self.etreerec.artist,
                    self.etreerec.source,
                    tracknum,
                    disc,
                    title,
                )
            )

        return args_list

    def _run_threads(
        self, args_list: Sequence[tuple], num_threads: Optional[int]
    ) -> None:
        if num_threads is None:
            cpu_count = os.cpu_count() or 1
            num_threads = max(1, cpu_count - 1)

        pbar = tqdm(total=len(args_list), desc="Tagging")
        try:
            with ThreadPoolExecutor(max_workers=num_threads) as ex:
                futures = {ex.submit(self.worker, *args): args[1] for args in args_list}
                for fut in as_completed(futures):
                    file_name = futures[fut]
                    pbar.update(1)
                    try:
                        name, success, error = fut.result()
                        if not success:
                            self.log.error(
                                f"Tagging failed for {name or file_name}: {error}"
                            )
                    except Exception as e:
                        self.log.error(
                            f"Multithreaded worker exception: {e}; File: {file_name}"
                        )
        finally:
            pbar.close()

    # # ---- tiny fallback ------------------------------------------------------

    # @staticmethod
    # def _fallback_extract_year(date_str: str) -> Optional[int]:
    #     import re
    #     from datetime import datetime
    #     s = date_str.strip()
    #     m = re.search(r"(\d{4})", s)
    #     if m:
    #         return int(m.group(1))
    #     m = re.search(r"(\d{2})$", s)
    #     if m:
    #         two = int(m.group(1))
    #         now_two = int(str(datetime.now().year)[-2:])
    #         return 2000 + two if two <= now_two else 1900 + two
    #     return None
