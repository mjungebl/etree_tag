from pathlib import Path
from recordingfiles import RecordingFolder
from sqliteetreedb import SQLiteEtreeDB
import logging
import os
from tqdm import tqdm
from concurrent.futures import (
    ThreadPoolExecutor, 
    as_completed,
)
import shutil
import re
from datetime import datetime
from typing import Optional
from services.config import (
    AppConfig, 
    load_app_config,
)
from services.exceptions import (
    ConfigurationError,
    FolderProcessingError,
    TaggerError,
)

# import InfoFileTagger
from tagger_utils import TitleBuilder
from services.metadata import MetadataImporter
from services.persistence import TrackMetadataRepository
from services.tagging import tag_file_worker, tag_artwork_worker

logger = logging.getLogger(__name__)

"""
This script provides functionality for tagging FLAC files with metadata and artwork using multithreading. 
It includes classes and functions to load configuration settings, find matching recordings, and tag files with album information and artwork.
Classes:
    ConcertTagger: A class to handle tagging of concert recordings with metadata and artwork.
Functions:
    load_config(config_path: str) -> dict:
    tag_file_worker(args):
        Worker function to add artwork and metadata to a single FLAC file using threads.
    tag_artwork_worker(args):
    ConcertTagger.__init__(self, concert_folder: str, config: dict, db: SQLiteEtreeDB):
    ConcertTagger._find_artwork(self, artist_abbr: str, concert_date: str):
    ConcertTagger.tag_artwork(self, clear_existing: bool = False, num_threads: int = None):
    ConcertTagger.tag_album(self, clear_existing: bool = True):
        Tag FLAC files with album information.
    ConcertTagger.tag_files(self, clear_existing_artwork: bool = False, clear_existing_tags: bool = True, num_threads: int = None):
        Add artwork and metadata to all FLAC files using multithreading.
    ConcertTagger.tag_shows(concert_folders: list, etree_db: SQLiteEtreeDB, config, clear_existing_artwork: bool = False, clear_existing_tags: bool = False):
        Process and tag multiple concert folders with metadata and artwork.
Example usage:
        # Load configuration and initialize database
        config_file = os.path.join(os.path.dirname(__file__), "config.toml")
        etreedb = SQLiteEtreeDB(r'db/etree_scrape.db')
        # Define concert folders to process
        concert_folders = sorted([f.path.replace('\\', '/') for f in os.scandir(parentfolder) if f.is_dir()])
        # Tag shows
            etreedb, config,
            clear_existing_artwork=False,
            clear_existing_tags=True
"""


def load_config(config_path: str) -> AppConfig:
    """Load configuration into a structured AppConfig dataclass."""
    try:
        return load_app_config(config_path)
    except Exception as exc:  # pragma: no cover - configuration errors are user-driven
        logger.error("Failed to load configuration from %s: %s", config_path, exc)
        raise ConfigurationError(f"Failed to load configuration from {config_path}") from exc


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


def remove_match_from_lists(lists, item):
    """
    Remove all occurrences of an item from the master list,
    and remove the corresponding elements from list2 and list3.

    Parameters:
        key_list (list): The master list to search for the item.
        list2 (list): The second list to remove corresponding elements.
        list3 (list): The third list to remove corresponding elements.
        item: The item to be removed.

    Returns:
        int: The number of occurrences removed.
    """
    # Get all indices where the item occurs in the master list.
    for list in lists:
        if item not in list:
            continue
        indices_to_remove = [i for i, v in enumerate(list) if v == item]
        break  # we have the items to remove, exit the loop

    # Remove items in reverse order to avoid index shifting issues.
    for i in reversed(indices_to_remove):
        for list in lists:
            if i < len(list):
                list.pop(i)

    return lists


class ConcertTagger:

    def __init__(
        self, concert_folder: str, config: dict, db: SQLiteEtreeDB, debug: bool = False
    ):
        """
        Initialize the ConcertTagger with a concert folder and a configuration dictionary.

        The configuration should contain:
            - artwork_folders: a dictionary mapping artist abbreviations to
              lists of directories (relative or absolute) to search for artwork.
              If an abbreviation has no entry, artwork tagging is skipped.
            - default_images: a mapping of artist abbreviations to fallback
              artwork paths.

        Args:
            concert_folder (str): Path to the folder containing concert files.
            config (dict): A dictionary with keys "artwork_folders" and
                "default_images".
        """
        self.config = config
        self.folderpath = Path(concert_folder)
        if not self.folderpath.is_dir():
            raise ValueError(f"{concert_folder} is not a valid directory.")
        alias_overrides = getattr(
            getattr(config, "recording_folder", None),
            "standardize_artist_abbrev",
            None,
        )
        self.folder = RecordingFolder(
            concert_folder,
            db,
            standardize_artist_abbrev=alias_overrides,
        )
        self.db = db
        self.repository = TrackMetadataRepository(db)
        self.metadata_importer = MetadataImporter(
            repository=self.repository,
            enable_filename_fallback=self.config.preferences.enable_filename_fallback,
        )
        self.NoMatch = False
        try:
            self.etreerec = self.folder._find_matching_recording(debug=debug)
        except Exception as exc:
            logger.exception(
                "Error locating matching recording for %s",
                self.folderpath.as_posix(),
            )
            self.NoMatch = True

        if not self.etreerec:
            self.NoMatch = True
        else:
            # standardize folder name if artist abbreviation and year are not
            # in the expected format
            try:
                self.folder._standardize_folder_year(self.etreerec)
                self.folderpath = self.folder.folder
            except Exception as e:
                logger.error("_standardize_folder_year failed: %s", e)
        # Store configuration for artwork search. ``artwork_folders`` maps
        # artist abbreviations to lists of directories. If an abbreviation is
        # not present, no artwork search will be performed for that artist.
        self.artwork_folders_map = config.cover.artwork_folders
        self.default_images_map = config.cover.default_images
        self.artwork_folders = []
        self.artworkpath = None
        self.errormsg = None

        if not self.NoMatch:
            try:
                if self.etreerec.date and self.etreerec.artist_abbrev:
                    # Select artwork folders for this artist. No fallback is
                    # used—if the abbreviation is not configured, we skip artwork
                    # tagging for this concert.
                    self.artwork_folders = self.artwork_folders_map.get(
                        self.etreerec.artist_abbrev, []
                    )
                    self.artworkpath = None
                    try:
                        self.artworkpath = self._find_artwork(
                            self.etreerec.artist_abbrev,
                            self.etreerec.date,
                        )
                    except FileNotFoundError as fnf_err:
                        logger.error("Artwork lookup failed: %s", fnf_err)
                        raise
                    if not self.artworkpath and not (
                        self.artwork_folders
                        or self.default_images_map.get(self.etreerec.artist_abbrev)
                    ):
                        logger.info(
                            "No artwork directories configured for artist %s",
                            self.etreerec.artist_abbrev,
                        )
                    elif not self.artworkpath:
                        raise FileNotFoundError(
                            f"No artwork found for {self.etreerec.artist_abbrev} on {self.etreerec.date}"
                        )
            except FileNotFoundError as e:
                logger.error("Artwork search failed: %s", e)
                raise
            except Exception as exc:
                logger.exception(
                    "Unexpected error while locating artwork for %s",
                    self.folderpath.as_posix(),
                )
                self.errormsg = (
                    f"No Matching recording found in database for folder {self.folderpath.as_posix()}"
                )
                raise TaggerError(
                    f"{exc} in _find_artwork for {self.folderpath.as_posix()}"
                ) from exc

        else:
            logger.error(
                "No Matching recording found in database for folder %s",
                self.folderpath.as_posix(),
            )
            self.errormsg = f"No Matching recording found in database for folder {self.folderpath.as_posix()}"
        # ... (other initializations such as finding FLAC files and auxiliary files)

    def _find_artwork(self, artist_abbr: str, concert_date: str):
        """
        Search for artwork based on a list of artwork directories defined in the configuration.

        The search works as follows:
          1. Extract the year from the concert_date (format "YYYY-MM-DD").
          2. For each folder in self.artwork_folders (in order), append the year.
          3. If that directory exists, search within it for a file matching the pattern:
             <artist_abbr><concert_date>* .jpg
             For example, if artist_abbr is "gd" and concert_date is "1975-03-23", then the
             pattern is "gd1975-03-23*.jpg".
          4. Return the first matching file found.
          5. If no matching file is found in any of the artwork folders, return the default image.

        Args:
            artist_abbr (str): The artist abbreviation (e.g. "gd").
            concert_date (str): The concert date in YYYY-MM-DD format.

        Returns:
            Path or None: The path to the artwork file if found. If no match is
            found but a per-artist default image is configured, that path is
            returned. If the configured default does not exist, a
            ``FileNotFoundError`` is raised. If no default is configured,
            ``None`` is returned.
        """
        year = concert_date.split("-")[0]
        for folder in self.artwork_folders:
            art_dir = Path(folder) / year
            if art_dir.exists() and art_dir.is_dir():
                # Build a pattern: artist_abbr + concert_date + anything + .jpg
                pattern = f"{artist_abbr}{concert_date}*.jpg"
                candidates = list(art_dir.glob(pattern))
                if candidates:
                    # Optionally, sort candidates and return the first one.
                    candidates.sort()
                    return candidates[0]
        # If nothing was found in the artwork folders, check for a per-artist
        # default image. If configured but the file does not exist, raise an
        # error so the caller knows artwork tagging cannot proceed.
        default_path_str = self.default_images_map.get(artist_abbr)
        if default_path_str:
            default_path = Path(default_path_str)
            if default_path.exists() and default_path.is_file():
                return default_path
            raise FileNotFoundError(
                f"Default artwork {default_path} not found for artist {artist_abbr}"
            )

        # If no default path was configured, return None so the caller can
        # decide whether to skip tagging or raise an error.
        return None

    def _stage_artwork(
        self, clear_existing_artwork: bool, retain_existing_artwork: bool
    ) -> Optional[str]:
        """Prepare folder artwork and return the image path to use during tagging."""
        if not self.artworkpath:
            logger.debug("No artwork file found to tag.")
            return None

        artwork_path_str = str(self.artworkpath)
        folder_path_str = str(self.folderpath)
        artwork_ext = os.path.splitext(artwork_path_str)[1].lower()
        artwork_formats = ["jpg", "jpeg", "png", "gif", "bmp", "webp"]

        existing_artworks = [
            os.path.join(folder_path_str, f"folder.{ext}")
            for ext in artwork_formats
            if os.path.exists(os.path.join(folder_path_str, f"folder.{ext}"))
        ]

        if existing_artworks:
            logger.debug("Existing artwork files found: %s", existing_artworks)
            if not clear_existing_artwork:
                logger.debug(
                    "Existing artwork found (%s), and replacement is disabled. Skipping new artwork.",
                    existing_artworks,
                )
                return existing_artworks[0]

            for existing_artwork in existing_artworks:
                if retain_existing_artwork:
                    backup_name = f"{existing_artwork}.old"
                    os.rename(existing_artwork, backup_name)
                    logger.debug("Renamed %s to %s", existing_artwork, backup_name)
                else:
                    os.remove(existing_artwork)
                    logger.debug("Deleted existing artwork %s", existing_artwork)
            dest_ext = os.path.splitext(existing_artworks[0])[1].lower()
        else:
            dest_ext = artwork_ext

        dest_file = os.path.join(folder_path_str, f"folder{dest_ext}")
        try:
            if os.path.exists(dest_file) and not clear_existing_artwork:
                logger.debug(
                    "%s already exists. Not replacing due to retention policy.",
                    dest_file,
                )
            elif not os.path.exists(dest_file):
                shutil.copy2(artwork_path_str, dest_file)
                logger.info("Copied new artwork to %s.", dest_file)
        except FileNotFoundError as e:
            logger.error(
                "Error copying artwork file %s to %s: %s",
                artwork_path_str,
                dest_file,
                e,
            )
            return None

        return dest_file






    def tag_artwork(self, num_threads: int = None):
        """
        Add artwork to FLAC files and copy it to the folder with retention preferences.

        See `config.toml` for artwork preferences:
        - `clear_existing_artwork`: If True, removes existing artwork tag and folder image before adding a new one.
        - `retain_existing_artwork`: If True, renames old folder images instead of deleting them (folder.<ext>.old).
        - `artwork_folders`: Directories to search for matching artwork,
          organized by artist abbreviation.
        - `default_images`: Mapping of artist abbreviations to fallback artwork
          images.

        Args:
            num_threads (int, optional): Number of threads to use. Defaults to os.cpu_count()-1.
        """

        clear_existing_artwork = self.config.cover.clear_existing_artwork
        retain_existing_artwork = self.config.cover.retain_existing_artwork

        artwork_path_str = self._stage_artwork(
            clear_existing_artwork, retain_existing_artwork
        )
        if not artwork_path_str:
            return

        args_list = [
            (file.path, file.name, artwork_path_str, clear_existing_artwork)
            for file in self.folder.musicfiles
        ]

        if num_threads is None:
            cpu_count = os.cpu_count() or 1
            num_threads = max(1, cpu_count - 1)

        tickers = len(args_list)
        pbar = tqdm(total=tickers, desc="Tagging Artwork")

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {
                executor.submit(tag_artwork_worker, args): args[1]
                for args in args_list
            }
            for future in as_completed(futures):
                file_name = futures[future]
                pbar.update(n=1)
                try:
                    name, success, error = future.result()
                    if not success:
                        logger.error(
                            f"Error tagging artwork for {name}: {error or 'Unknown error'}"
                        )
                except Exception as exc:  # pragma: no cover - worker failure path
                    error = str(exc)
                    logger.exception(
                        "Multithreaded tag_artwork_worker call failed for %s",
                        file_name,
                    )
        pbar.close()

    def tag_files(self, clear_existing_tags: bool = True, num_threads: int = None):
        """
        Add artwork and metadata to all FLAC files using multithreading.

        Args:
            clear_existing_tags (bool): If True, remove all tags from the files prior to adding tags.
            num_threads (int, optional): Number of threads to use. Defaults to os.cpu_count()-1.
        """

        tb = TitleBuilder(self.etreerec, self.folder, self.config.to_mapping())
        album = tb.generate_title()
        logger.debug("Album title resolved as %s", album)
        if not self.etreerec.tracks:
            logger.warning(
                "No track metadata found in %s for %s. Attempting to parse the info file.",
                self.repository.db_path,
                self.folderpath.as_posix(),
            )
            self.metadata_importer.import_metadata(self)
            logger.info(
                "Successfully derived track metadata from local files for %s.",
                self.folderpath.as_posix(),
            )
        logger.info(
            "Tagging %s in %s",
            album,
            self.folderpath.as_posix(),
        )

        genretag = None
        if self.etreerec.date:
            if len(self.etreerec.date) > 4 and self.etreerec.artist == "Grateful Dead":
                album_year = extract_year(self.etreerec.date)
                genretag = f"gd{str(album_year)}"

        clear_existing_artwork = self.config.cover.clear_existing_artwork
        retain_existing_artwork = self.config.cover.retain_existing_artwork

        artwork_path_str = self._stage_artwork(
            clear_existing_artwork, retain_existing_artwork
        )

        segue = self.config.preferences.segue_string or ">"
        gazinta_abbrev = segue

        args_list = []
        for file in self.folder.musicfiles:
            song_info = self.etreerec.get_track_by_checksum(file.checksum)
            tracknum, disc, title = None, None, None
            if song_info:
                title = song_info.title
                if song_info.gazinta:
                    title = f"{title} {gazinta_abbrev}"
                tracknum, disc = song_info.tracknum, song_info.disc
            args_list.append(
                (
                    file.path,
                    file.name,
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

        if num_threads is None:
            cpu_count = os.cpu_count() or 1
            num_threads = max(1, cpu_count - 1)

        tickers = len(args_list)
        pbar = tqdm(total=tickers, desc="Tagging")
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {
                executor.submit(tag_file_worker, args): args[1] for args in args_list
            }
            for future in as_completed(futures):
                file_name = futures[future]
                pbar.update(n=1)
                try:
                    name, success, error = future.result()
                except Exception as exc:  # pragma: no cover - worker failure path
                    logger.exception(
                        "Multithreaded tag_file_worker call failed for %s",
                        file_name,
                    )
        pbar.close()

    def tag_shows_debug(
        concert_folders: list,
        etree_db: SQLiteEtreeDB,
        config,
        clear_existing_tags: bool = False,
    ):
        """
        Tags concert folders with metadata from the etree database.
        Args:
            concert_folders (list): List of paths to concert folders to be tagged.
            etree_db (SQLiteEtreeDB): Instance of the SQLiteEtreeDB class for database access.
            config: Configuration settings for tagging.
            clear_existing_tags (bool, optional): If True, existing tags will be cleared before tagging. Defaults to False.
        Raises:
            Exception: If an error occurs during the tagging process, it will be logged.
        """
        folder_count = len(concert_folders)

        logger.info("Processing tags for %d folders.", folder_count)
        for index, concert_folder in enumerate(concert_folders, start=1):
            logger.debug("-" * 78)
            logger.info(
                "Processing (%d/%d): %s",
                index,
                folder_count,
                Path(concert_folder).name,
            )

            tagger = ConcertTagger(concert_folder, config, etree_db)
            if not tagger.errormsg:
                tagger.tag_files(clear_existing_tags=clear_existing_tags)
            else:
                logger.error(
                    "Tagger reported error for %s: %s",
                    concert_folder,
                    tagger.errormsg,
                )

    def tag_shows(
        concert_folders: list,
        etree_db: SQLiteEtreeDB,
        config,
        clear_existing_tags: bool = False,
    ):
        """
        Tags concert folders with metadata from the etree database.
        Args:
            concert_folders (list): List of paths to concert folders to be tagged.
            etree_db (SQLiteEtreeDB): Instance of the SQLiteEtreeDB class for database access.
            config: Configuration settings for tagging.
            clear_existing_tags (bool, optional): If True, existing tags will be cleared before tagging. Defaults to False.
        Raises:
            FolderProcessingError: When one or more folders fail to process.
        """
        folder_count = len(concert_folders)
        errors: list[tuple[str, Exception]] = []

        logger.info("Processing tags for %d folders.", folder_count)
        for index, concert_folder in enumerate(concert_folders, start=1):
            folder_name = Path(concert_folder).name
            logger.info(
                "Processing (%d/%d): %s",
                index,
                folder_count,
                folder_name,
            )
            try:
                tagger = ConcertTagger(concert_folder, config, etree_db)
                if getattr(tagger, "errormsg", None):
                    raise TaggerError(tagger.errormsg)
                tagger.tag_files(clear_existing_tags=clear_existing_tags)
            except TaggerError as exc:
                logger.error("Tagging error for %s: %s", folder_name, exc)
                errors.append((concert_folder, exc))
            except Exception as exc:  # pragma: no cover - defensive orchestration
                logger.exception(
                    "Unexpected error processing folder %s", concert_folder
                )
                errors.append((concert_folder, exc))

        if errors:
            summary = "; ".join(
                f"{Path(folder).name}: {error}" for folder, error in errors
            )
            raise FolderProcessingError(
                f"Failed to tag {len(errors)} folder(s): {summary}"
            )

    def build_show_inserts(self):
        """
        Build show inserts for the concert folder.
        """
        shnid = self.etreerec.id
        records = []
        for file in self.folder.musicfiles:
            # shnid_val, disc_number, track_number, title, fingerprint, bit_depth, frequency, length_val, channels, filename = rec
            records.append(
                (
                    shnid,
                    file.disc,
                    file.tracknum,
                    file.title,
                    file.checksum,
                    file.audio.info.bits_per_sample,
                    file.audio.info.sample_rate,
                    file.length,
                    file.audio.info.channels,
                    file.name,
                )
            )
        return records




