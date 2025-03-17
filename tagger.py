from pathlib import Path
from recordingfiles import RecordingFolder
from sqliteetreedb import SQLiteEtreeDB, EtreeRecording
import logging
import tomllib
from mutagen.flac import Picture, FLAC
import os
from tqdm import tqdm
#from concurrent.futures import ProcessPoolExecutor, as_completed
#import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import re
from datetime import datetime
"""
This script provides functionality for tagging FLAC files with metadata and artwork using multithreading. 
It includes classes and functions to load configuration settings, find matching recordings, and tag files with album information and artwork.
Classes:
    ConcertTagger: A class to handle tagging of concert recordings with metadata and artwork.
Functions:
    load_config(config_path: str) -> dict:
    _tag_file_thread(args):
        Worker function to add artwork and metadata to a single FLAC file using threads.
    _tag_artwork_for_file_thread(args):
    ConcertTagger.__init__(self, concert_folder: str, config: dict, db: SQLiteEtreeDB):
    ConcertTagger._find_artwork(self, artist_abbr: str, concert_date: str):
    ConcertTagger._find_matching_recording(self):
        Find a matching recording in the database based on checksums.
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


def load_config(config_path: str) -> dict:
    """
    Load a TOML configuration file and return the configuration as a dictionary.

    Args:
        config_path (str): The path to the TOML configuration file.

    Returns:
        dict: A dictionary containing the configuration settings.
    """
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        return config
    
    except Exception as e:
        print(f"Error loading configuration: {e}")
        raise    


def extract_year(date_str):
    # Remove any leading/trailing whitespace.
    date_str = date_str.strip()
    
    # First, try to parse the string as a valid ISO date (YYYY-MM-DD).
    try:
        valid_date = datetime.strptime(date_str, "%Y-%m-%d")
        return valid_date.year
    except ValueError:
        # If it fails, fall back to extracting a two-digit year.
        pass

    # Look for a two-digit year pattern at the end of the string.
    match = re.search(r'(\d{2})$', date_str)
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


def remove_match_from_lists(key_list, list2, list3, item):
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
    indices_to_remove = [i for i, v in enumerate(key_list) if v == item]
    
    # Remove items in reverse order to avoid index shifting issues.
    for i in reversed(indices_to_remove):
        key_list.pop(i)
        list2.pop(i)
        list3.pop(i)
    
    return (key_list, list2, list3)

def _tag_file_thread(args):
    """
    Worker function to add artwork to a single FLAC file using threads.

    Args:
        args (tuple): Contains:
        - file_path (str): Full path to the FLAC file.
        - file_name (str): File name (for logging).
        - artwork_path (str): Full path to the artwork image.
        - clear_existing (bool): If True, clear any existing artwork before adding.
        
    Returns:
        tuple: (file_name, success (bool), error (str or None))
    """
    #(file.path, file.name, artwork_path_str, clear_existing_artwork, clear_existing_tags,album, genretag, file.title, file.tracknum, file.disc, self.etreerec.artist)        
    file_path, file_name, artwork_path, clear_existing_artwork, clear_existing_tags,album, genretag, artist, source,tracknum, disc, title = args
    try:
                
        # Read artwork from disk.
        if artwork_path:
            try:
                with open(artwork_path, "rb") as f:
                    image_data = f.read()
            except Exception as e:
                logging.error(f"Error reading artwork file {artwork_path}: {e}")
        else:
            image_data = None
            logging.info("No artwork file found to tag.")
            #return
        # Open the FLAC file.
        audio = FLAC(file_path)
        if clear_existing_artwork and audio.pictures and image_data:
            # Clear existing artwork if specified and we have a new image.
            audio.clear_pictures()
            logging.info(f"Cleared artwork from file: {file_name}")

        # Clear all tags (this removes the Vorbis comments)
        if clear_existing_tags:
            for key in list(audio.keys()):
                # Skip deleting the artwork if it appears as a tag.
                if key.lower() == "metadata_block_picture":
                    continue
                del audio[key]
            logging.info(f"Cleared tags from file: {file_name}")

        if image_data:
            # Add new artwork if it doesn't already exist.
            if not audio.pictures:
            # Create a Picture object.
                pic = Picture()
                pic.type = 3  # Cover (front)
                pic.mime = "image/jpeg"  # Adjust if your artwork is in a different format.
                pic.data = image_data                
                audio.add_picture(pic)
                logging.info(f"Added artwork to file: {file_name}")
            else:
                logging.info(f"Artwork already exists in file: {file_name}")

        audio["album"] = album
        audio["artist"] = artist #may need an override here for the JGB type stuff
        audio["albumartist"] = artist
        if "album artist" in audio: #clear anything that might've already been there to clean up artist menu
            del audio["album artist"]
        audio["comment"] = source
        if genretag:
            audio["genre"] = genretag

        #tracknum, disc, title
        if title:
        #print(f'Song details: {song_info.title} {song_info.disc} {song_info.tracknum}')
            if title:
                audio["title"] = title    # Track name
            if disc:
                audio["discnumber"] = disc                # Disc number (as a string)
            if tracknum:
                audio["tracknumber"] = tracknum               # Track number (as a string)
        else:
            logging.error(f"Error tagging song details {file_path}: No matching track data found in database")
        audio.save()
        return (file_name, True, None)
    except Exception as e:
        logging.error(f"Error tagging file {file_name}: {e}")
        return (file_name, False, str(e))


def _tag_artwork_for_file_thread(args):
    """
    Worker function to add artwork to a single FLAC file using threads.

    Args:
        args (tuple): Contains:
          - file_path (str): Full path to the FLAC file.
          - file_name (str): File name (for logging).
          - artwork_path (str): Full path to the artwork image.
          - clear_existing (bool): If True, clear any existing artwork before adding.
          
    Returns:
        tuple: (file_name, success (bool), error (str or None))
    """
    file_path, file_name, artwork_path, clear_existing = args
    try:
        # Read artwork from disk.
        try:
            with open(artwork_path, "rb") as f:
                image_data = f.read()
        except Exception as e:
            logging.error(f"Error reading artwork file {artwork_path}: {e}")
            return

        # Create a Picture object.
        pic = Picture()
        pic.type = 3  # Cover (front)
        pic.mime = "image/jpeg"  # Adjust if your artwork is in a different format.
        pic.data = image_data

        # Open the FLAC file.
        audio = FLAC(file_path)
        if clear_existing and audio.pictures:
            audio.clear_pictures()
            logging.info(f"Cleared artwork from file: {file_name}")

        if not audio.pictures:
            audio.add_picture(pic)
            audio.save()
            logging.info(f"Added artwork to file: {file_name}")
        else:
            logging.info(f"Artwork already exists in file: {file_name}")
        return (file_name, True, None)
    except Exception as e:
        logging.error(f"Error tagging file {file_name}: {e}")
        return (file_name, False, str(e))


class ConcertTagger:
    def __init__(self, concert_folder: str, config: dict, db:SQLiteEtreeDB):
        """
        Initialize the ConcertTagger with a concert folder and a configuration dictionary.
        
        The configuration should contain:
            - artwork_folders: a list of directories (relative or absolute) to search for artwork.
            - defaultimage_path: the path to a default artwork image.
        
        Args:
            concert_folder (str): Path to the folder containing concert files.
            config (dict): A dictionary with keys "artwork_folders" and "defaultimage_path".
        """
        self.config = config
        self.folderpath = Path(concert_folder)
        if not self.folderpath.is_dir():
            raise ValueError(f"{concert_folder} is not a valid directory.")        
        self.folder = RecordingFolder(concert_folder)
        self.db = db
        self.NoMatch = False
        try:
            self.etreerec = self._find_matching_recording()
        except Exception as e:
            #raise(f'Error in ConcertTagger Init {e}')
            print (f'Error in ConcertTagger Init _find_matching_recording {e}')
            self.NoMatch = True
        if not self.etreerec:
            self.NoMatch = True
        # Store configuration for artwork search.
        self.artwork_folders = config["cover"]["artwork_folders"]
        self.defaultimage_path = config["cover"]["defaultimage_path"]
        self.artworkpath = None
        self.errormsg = None

        if not self.NoMatch: #doh, double negative
            #TODO fix this for other artists, config file work will be needed as well.
            try:
                if self.etreerec.date and self.etreerec.artist == 'Grateful Dead':
                    self.artworkpath = self._find_artwork('gd',self.etreerec.date)
            except Exception as e:
                logging.error(f'Exception: {e} in _find_artwork for {self.folderpath.as_posix()}')
                print(f'Exception: {e} in _find_artwork for {self.folderpath.as_posix()}')
                self.errormsg = f'No Matching recording found in database for folder {self.folderpath.as_posix()}'
                raise Exception(f'{e} in _find_artwork for {self.folderpath.as_posix()}')
                
        else:
            logging.error(f'No Matching recording found in database for folder {self.folderpath.as_posix()}')
            self.errormsg = f'No Matching recording found in database for folder {self.folderpath.as_posix()}'
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
            Path or None: The path to the artwork file if found, otherwise the default artwork file
                          (if it exists), or None.
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
        # If nothing was found in the artwork folders, fall back to the default image.
        default_path = Path(self.defaultimage_path)
        if default_path.exists() and default_path.is_file():
            return default_path
        return None
    
    def _find_matching_recording(self):
        #TODO:Move this function to etreedb?
        if self.folder.checksums:
            matches,b_mismatch_exists = self.db.get_local_checksum_matches(self.folder.checksums)
            checksummatches = set()
            if not b_mismatch_exists: #return an empty list if one of the files is a mismatch
            #TODO: add explanation of mismatch, maybe another function call?
                for match in matches:
                    try:
                        rec = EtreeRecording(self.db,match)
                    except Exception as e:
                        raise Exception (f'Error encoiuntered for {self.folderpath}')
                        #continue
                    for sig in rec.checksums:
                        if set(sig.checksumlist) == set(self.folder.checksums):
                            print (f"Match found: {sig.filename} md5key={sig.id} shnid={sig.shnid}")
                            if rec.tracks: #take the first match that is identical and has the tracks listed because everything can presumably be tagged
                                return rec
                            checksummatches.add((sig.shnid,sig.id))
                            break #only need 1 match per shnid
            #print(list(checksummatches)) #change to return if using 2 functions?
            #TODO, make this a second function?
            etreerec = None
            for shnid, dummy in checksummatches:
                etreerec = EtreeRecording(self.db,shnid)
                if self.folder.foldershnid == etreerec.id:
                    print(f'Exact match found for shnid {etreerec.id} in folder name') #might as well use the folder
                    logging.info(f'Exact match found for shnid {etreerec.id} in folder name')
                    return etreerec
                print(f'No EXACT MATCH found for shnid {self.folder.foldershnid} using {etreerec.id}')
                logging.warn(f'No EXACT MATCH found for shnid {self.folder.foldershnid} using {etreerec.id}')
            return etreerec
        else:
            return None

    def tag_artwork(self, num_threads: int = None):
        """ 
        Add artwork to FLAC files and copy it to the folder with retention preferences.

        See `config.toml` for artwork preferences:
        - `clear_existing_artwork`: If True, removes existing artwork tag and folder image before adding a new one.
        - `retain_existing_artwork`: If True, renames old folder images instead of deleting them (folder.<ext>.old).
        - `artwork_folders`: Directories to search for matching artwork.
        - `defaultimage_path`: Fallback image if no match is found.

        Args:
            num_threads (int, optional): Number of threads to use. Defaults to os.cpu_count()-1.
        """

        # Load artwork preferences from config file
        clear_existing_artwork = self.config["cover"].get("clear_existing_artwork", False)
        retain_existing_artwork = self.config["cover"].get("retain_existing_artwork", True)

        # Check if we have replacement artwork available
        if not self.artworkpath:
            logging.info("No artwork file found to tag. Exiting function.")
            return

        artwork_path_str = str(self.artworkpath)
        artwork_ext = os.path.splitext(artwork_path_str)[1].lower()  # Preserve original extension

        # Check for existing artwork (file) using common file types (order of popularity)
        artwork_formats = ["jpg", "jpeg", "png", "gif", "bmp", "webp"]
        existing_artworks = [
            os.path.join(self.folderpath, f"folder.{ext}") 
            for ext in artwork_formats if os.path.exists(os.path.join(self.folderpath, f"folder.{ext}"))
        ]

        logging.info(f"Existing artwork files found: {existing_artworks}")  # Debugging log

        # If artwork already exists and we are NOT clearing it, exit early
        if existing_artworks and not clear_existing_artwork:
            logging.info(f"Existing artwork found ({existing_artworks}), and replacement is disabled. Skipping copy.")
            return  # Exit immediately—NO new folder.jpg should be created

        # Determine correct artwork destination file based on existing format (if present)
        if existing_artworks:
            existing_ext = os.path.splitext(existing_artworks[0])[1].lower()  # Use the first existing file's extension
            dest_file = os.path.join(self.folderpath, f"folder{existing_ext}")
        else:
            dest_file = os.path.join(self.folderpath, f"folder{artwork_ext}")  # Default to the same format as new artwork

        # If we are clearing existing artwork, handle renaming or deleting old files
        if clear_existing_artwork and existing_artworks:
            for existing_artwork in existing_artworks:
                if retain_existing_artwork:  # Retain old artwork by renaming it
                    backup_name = f"{existing_artwork}.old"
                    os.rename(existing_artwork, backup_name)
                    logging.info(f"Renamed {existing_artwork} to {backup_name}")
                else:  # Delete existing artwork
                    os.remove(existing_artwork)
                    logging.info(f"Deleted existing artwork {existing_artwork}")

        # 🚨 **Prevent overwriting if we already have artwork in the correct format**
        if os.path.exists(dest_file):
            logging.info(f"{dest_file} already exists. Not replacing due to retention policy.")
            return

        # Copy the new artwork file to the destination folder
        shutil.copy2(artwork_path_str, dest_file)
        logging.info(f"Copied new artwork to {dest_file}.")

        # Tag artwork in FLAC files
        args_list = [(file.path, file.name, artwork_path_str, clear_existing_artwork) for file in self.folder.musicfiles]
        num_threads = num_threads or (os.cpu_count() or 1) - 1
        tickers = len(args_list)
        pbar = tqdm(total=tickers, desc='Tagging Artwork')

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {executor.submit(_tag_artwork_for_file_thread, args): args[1] for args in args_list}
            for future in as_completed(futures):
                file_name = futures[future]
                pbar.update(n=1)
                try:
                    name, success, error = future.result()
                except Exception as e:
                    success = False
                    error = str(e)
                    logging.error(f"Multithreaded _tag_artwork_for_file_thread call: {e} File: {file_name}")
        pbar.close()



    def tag_album(self, clear_existing: bool = True):
        #TODO customise this string (separate function?)
        #print(f'{self.etreerec.date=}')
        album = f'{self.etreerec.date} {self.etreerec.etreevenue} {'('+self.folder.recordingtype+') ' if self.folder.recordingtype else ''}{'['+str(self.folder.musicfiles[0].audio.info.bits_per_sample)+'-'+
                                                                   str(self.folder.musicfiles[0].audio.info.sample_rate).rstrip('0')+
                                                                   '] ' if self.folder.musicfiles and str(self.folder.musicfiles[0].audio.info.bits_per_sample) != '16' else ''}{'('+str(self.etreerec.id)+')'}'
        print(f'{album=}')
        if not self.etreerec.tracks:
            print(f'ERROR: Unable to tag track names. No Metadata found in {self.db.db_path} for {self.folderpath.as_posix()}')
            logging.error(f'No track metadata found in {self.db.db_path} for: {self.folderpath.as_posix()}')
        logging.info(f'Tagging {album} in {self.folderpath.as_posix()}')
        genretag = None
        if self.etreerec.date:
            #todo: chenge this to something configurable and add other artists. 
            if len(self.etreerec.date) > 4:
                genretag = f"gd{str(self.etreerec.date[0:4])}"
        if album:
            
            for file in self.folder.musicfiles:
                
                try:
                    file.audio["album"] = album
                    file.audio["artist"] = self.etreerec.artist
                    file.audio["albumartist"] = self.etreerec.artist
                    if "album artist" in file.audio: #clear anything that might've already been there to clean up artist menu
                        del file.audio["album artist"]
                    file.audio["comment"] = self.etreerec.source
                    if genretag:
                        file.audio["genre"] = genretag
                    print(file.checksum, self.etreerec.id)                        
                    if self.etreerec.tracks:
                        song_info =self.etreerec.get_track_by_checksum(file.checksum)
                        
                        if song_info:
                            print(f'Song details: {song_info.title} {song_info.disc} {song_info.tracknum}')
                            if song_info.title:
                                file.audio["title"] = song_info.title    # Track name
                            if song_info.disc:
                                file.audio["discnumber"] = song_info.disc                # Disc number (as a string)
                            if song_info.tracknum:
                                file.audio["tracknumber"] = song_info.tracknum               # Track number (as a string)
                        else:
                            logging.error(f"Error tagging song details {file.path}: No matching track data found in database")
                    file.audio.save()
                except Exception as e:
                    logging.error(f"Error tagging file {file.path}: {e}")
        else:
            logging.info(f'Skipped tags: No Album generated for folder {self.folderpath.as_posix()}')

    def generate_title(self):
        # Extract values from the [preferences] section.
        year_format = config["preferences"].get("year_format",None)
        soundboard_abbrev = config["preferences"].get("soundboard_abbrev",None)
        aud_abbrev = config["preferences"].get("aud_abbrev",None)
        matrix_abbrev = config["preferences"].get("matrix_abbrev",None)
        ultramatrix_abbrev = config["preferences"].get("ultramatrix_abbrev",None)

        # Extract values from the [album_tag] section.
        include_bitrate = config["album_tag"].get("include_bitrate",True)
        include_bitrate_not16_only = config["album_tag"].get("include_bitrate_not16_only",True)
        include_venue = config["album_tag"].get("include_venue",True)
        include_city = config["album_tag"].get("include_city",True)
        include_shnid = config["album_tag"].get("include_shnid",True)
        order = config["album_tag"].get("order",None)
        prefix = config["album_tag"].get("prefix",None)
        suffix = config["album_tag"].get("suffix",None)
        title_year = extract_year(self.etreerec.date)
        show_date = self.etreerec.date

        #if the date is in the incorrect format, make an attempt to fix it for the title
        if title_year:
            if str(title_year) != self.etreerec.date[0:4]:
                
                if '/' in self.etreerec.date:
                    splitter = '/'
                elif '-' in self.etreerec.date:
                    splitter = '-'
                if splitter:
                    show_date_parts = self.etreerec.date.split(splitter)
                    #print(f'{show_date_parts=}')
                    if len(show_date_parts) == 3:
                        show_date = f"{str(title_year)}-{show_date_parts[0]}-{show_date_parts[1]}"
        if year_format.lower() == 'yy':
            show_date = show_date[2:]
        #if the order is peecified and the prefix and suffix values are the same length, build the format string        
        recording_type = self.folder.recordingtype
        if recording_type:
            if recording_type.lower() == 'sbd' and soundboard_abbrev:
                recording_type = soundboard_abbrev
            elif recording_type.lower() == 'aud' and aud_abbrev:
                recording_type = aud_abbrev
            elif recording_type.lower() == 'matrix' and matrix_abbrev:
                recording_type = matrix_abbrev
            elif recording_type.lower() == 'ultramatrix' and ultramatrix_abbrev:
                recording_type = ultramatrix_abbrev
        city = self.etreerec.city
        venue = self.etreerec.etreevenue
        shnid = self.etreerec.id
        bitrate = f'{str(self.folder.musicfiles[0].audio.info.bits_per_sample)}-{str(self.folder.musicfiles[0].audio.info.sample_rate).rstrip("0")}'
        if include_bitrate_not16_only and str(self.folder.musicfiles[0].audio.info.bits_per_sample) == '16':
            include_bitrate = False
        #clean up the order list to remove any empty strings or None values
        if (not include_venue or not venue) and 'venue' in order:
            remove_match_from_lists(order, prefix, suffix, 'venue')
        if (not include_city or not city) and 'city' in order:
            remove_match_from_lists(order, prefix, suffix, 'city')
        #no need to check for an empty shnid or bitrate, won't get here if no match or no files
        if not include_shnid and 'shnid' in order: 
            remove_match_from_lists(order, prefix, suffix, 'shnid')
        if not include_bitrate and 'bitrate' in order:
            remove_match_from_lists(order, prefix, suffix, 'bitrate')
        format_str = ''
        if len(order) == len(prefix) == len(suffix) and order:
            for i in range(len(order)):
                format_str = format_str + f"{prefix[i]}{'{'}{order[i]}{'}'}{suffix[i]}"
        else :
            format_str = None
        #print(f'{format_str=}')
        album = None
        try:
            if format_str:
                album = format_str.format(**locals())
        except Exception as e:
            logging.error(f"Error formatting album title. reverting to default logic. {shnid=}: {e}")
        if not album:
            # Default album title generation logic
            album = f'{show_date} {venue} {city} '
            if recording_type:
                album = album + f'{(recording_type)} '
            if include_bitrate and self.folder.musicfiles:
                if str(self.folder.musicfiles[0].audio.info.bits_per_sample) != '16' or not include_bitrate_not16_only:
                    album = album + f'[{bitrate}] '

            album = album + f'({str(shnid)})'

        return album


    def tag_files(self, clear_existing_tags: bool = True, num_threads: int = None):
        """
        Add artwork to all FLAC files using multithreading.

        Args:
            clear_existing_artwork (bool): If True, remove any existing artwork before adding the new image.
                                    If False, add artwork only if no artwork is present.
            clear_existing_tags (bool): If True, remove all tags from the files prior to adding tags. 
            NOTE: false does not prevent tags from being overwritten if there is a new value found. It will clear everything                 
            num_threads (int, optional): Number of threads to use. Defaults to os.cpu_count()-1.
        """
        album = self.generate_title()
        print(f'{album=}')
        
        if not self.etreerec.tracks:
            print(f'ERROR: Unable to tag track names. No Metadata found in {self.db.db_path} for {self.folderpath.as_posix()}')
            logging.error(f'No track metadata found in {self.db.db_path} for: {self.folderpath.as_posix()}')
        logging.info(f'Tagging {album} in {self.folderpath.as_posix()}')
        
        genretag = None
        
        if self.etreerec.date:
            
            #TODO: change this to something configurable and add other artists. 
            if len(self.etreerec.date) > 4 and self.etreerec.artist == 'Grateful Dead':
                album_year = extract_year(self.etreerec.date)
                genretag = f"gd{str(album_year)}"

        #handle the artwork (folder.jpg file)
        if not self.artworkpath:
            logging.warning("No artwork file found to tag.")
        clear_existing_artwork = self.config["cover"].get("clear_existing_artwork", False)
        retain_existing_artwork = self.config["cover"].get("retain_existing_artwork", True)
        artwork_path_str = str(self.artworkpath)        
        dest_file = os.path.join(self.folderpath.as_posix(), "folder.jpg")
        artwork_ext = os.path.splitext(artwork_path_str)[1].lower()  # Preserve original extension
        artwork_formats = ["jpg", "jpeg", "png", "gif", "bmp", "webp"]     

        existing_artworks = [
            os.path.join(self.folderpath, f"folder.{ext}") 
            for ext in artwork_formats if os.path.exists(os.path.join(self.folderpath, f"folder.{ext}"))
        ]
        if existing_artworks:
            logging.info(f"Existing artwork files found: {existing_artworks}")  # Debugging log


        # 🚨 **If artwork already exists and we are NOT clearing it, moake a note of this**
        if existing_artworks and not clear_existing_artwork:
             logging.info(f"Existing artwork found ({existing_artworks}), and replacement is disabled. Skipping copy.")

        # Determine correct artwork destination file based on existing format (if present)
 

        if existing_artworks:
            existing_ext = os.path.splitext(existing_artworks[0])[1].lower()  # Use the first existing file's extension
            dest_file = os.path.join(self.folderpath, f"folder{existing_ext}")
        else:
            dest_file = os.path.join(self.folderpath, f"folder{artwork_ext}")  # Default to the same format as new artwork

        # If we are clearing existing artwork, handle renaming or deleting old files
        if clear_existing_artwork and existing_artworks:
            for existing_artwork in existing_artworks:
                if retain_existing_artwork:  # Retain old artwork by renaming it
                    backup_name = f"{existing_artwork}.old"
                    os.rename(existing_artwork, backup_name)
                    logging.info(f"Renamed {existing_artwork} to {backup_name}")
                else:  # Delete existing artwork
                    os.remove(existing_artwork)
                    logging.info(f"Deleted existing artwork {existing_artwork}")

        # 🚨 **Prevent overwriting if we already have artwork in the correct format**
        if os.path.exists(dest_file):
            logging.info(f"{dest_file} already exists. Not replacing due to retention policy.")
        # Copy the new artwork file to the destination folder
        else:
            shutil.copy2(artwork_path_str, dest_file)
            logging.info(f"Copied new artwork to {dest_file}.")

        # Build argument list using the files from your folder's musicfiles attribute.
        if self.config["preferences"]["segue_string"]:
            gazinta_abbrev = self.config["preferences"]["segue_string"]
        else:
            gazinta_abbrev = '>'
        args_list = []
        for file in self.folder.musicfiles:
            song_info = self.etreerec.get_track_by_checksum(file.checksum)
            #print(file.name, self.etreerec.id, [track.title for track in self.etreerec.tracks if track.fingerprint == file.checksum][0])
            tracknum, disc, title = None, None, None
            if song_info:
                tracknum, disc, title = song_info.tracknum, song_info.disc,f'{song_info.title}{' ' + gazinta_abbrev if song_info.gazinta else ''}'
            args_list.append((file.path, file.name, artwork_path_str, clear_existing_artwork, clear_existing_tags,
             album, genretag, self.etreerec.artist, self.etreerec.source,tracknum, disc, title))
            #print(song_info.title, song_info.gazinta)
        
        #for args in args_list:
        #    print(args[1])
        if num_threads is None:
            cpu_count = os.cpu_count() or 1
            num_threads = max(1, cpu_count - 1)
        tickers = len(args_list)
        pbar = tqdm(total=tickers, desc='Tagging')
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {executor.submit(_tag_file_thread, args): args[1] for args in args_list}
            for future in as_completed(futures):
                file_name = futures[future]
                pbar.update(n=1)
                try:
                    name, success, error = future.result()
                except Exception as e:
                    #name = file_name
                    #success = False
                    #error = str(e)
                    logging.error(f"Multithreaded _tag_file_thread call: {e}, File: {file_name}")
        pbar.close()

    def tag_shows_debug(
        concert_folders:list, 
        etree_db:SQLiteEtreeDB, 
        config,
        clear_existing_tags: bool = False
    ):
        """
        Tags concert folders with metadata from the etree database.
        Args:
            concert_folders (list): List of paths to concert folders to be tagged.
            etree_db (SQLiteEtreeDB): Instance of the SQLiteEtreeDB class for database access.
            config: Configuration settings for tagging.
            clear_existing_artwork (bool, optional): If True, existing artwork will be cleared before tagging. Defaults to False.
            clear_existing_tags (bool, optional): If True, existing tags will be cleared before tagging. Defaults to False.
        Raises:
            Exception: If an error occurs during the tagging process, it will be logged.
        """        
        folder_count = len(concert_folders)
        currentcount = 0
        
        print(f"Processing tags for {folder_count} folders.")
        for concert_folder in concert_folders:
            currentcount = currentcount + 1
            print("------------------------------------------------------------------------------")
            print(f"Processing ({currentcount}/{folder_count}): {Path(concert_folder).name}")
            #try:
            tagger = ConcertTagger(concert_folder, config, etree_db)
            if not tagger.errormsg:
                tagger.tag_files(clear_existing_tags=clear_existing_tags)
            else:
                logging.error (f'tagger.errormsg: {tagger.errormsg}')
            # except Exception as e:
            #     if e:
            #         logging.error(f'Error Processing folder {concert_folder} {e}')
            #     else:
            #         logging.error(f'Error Processing folder {concert_folder}')

    def tag_shows(
        concert_folders:list, 
        etree_db:SQLiteEtreeDB, 
        config,
        clear_existing_tags: bool = False
    ):
        """
        Tags concert folders with metadata from the etree database.
        Args:
            concert_folders (list): List of paths to concert folders to be tagged.
            etree_db (SQLiteEtreeDB): Instance of the SQLiteEtreeDB class for database access.
            config: Configuration settings for tagging.
            clear_existing_artwork (bool, optional): If True, existing artwork will be cleared before tagging. Defaults to False.
            clear_existing_tags (bool, optional): If True, existing tags will be cleared before tagging. Defaults to False.
        Raises:
            Exception: If an error occurs during the tagging process, it will be logged.
        """        
        folder_count = len(concert_folders)
        currentcount = 0
        
        print(f"Processing tags for {folder_count} folders.")
        for concert_folder in concert_folders:
            currentcount = currentcount + 1
            print("------------------------------------------------------------------------------")
            print(f"Processing ({currentcount}/{folder_count}): {Path(concert_folder).name}")
            try:
                tagger = ConcertTagger(concert_folder, config, etree_db)
                if not tagger.errormsg:
                    tagger.tag_files(clear_existing_tags=clear_existing_tags)
                else:
                    logging.error (f'tagger.errormsg: {tagger.errormsg}')
            except Exception as e:
                if e:
                    logging.error(f'Error Processing folder {concert_folder} {e}')
                else:
                    logging.error(f'Error Processing folder {concert_folder}')

if __name__ == "__main__":
    from time import perf_counter
    start_time = perf_counter()
    logfilename = 'tag_log.log' 
    logging.basicConfig(filename=logfilename,level=logging.WARN, format="%(asctime)s %(levelname)s: %(message)s")
    config_file = os.path.join(os.path.dirname(__file__),"config.toml")
    config = load_config(config_file)


    etreedb = SQLiteEtreeDB(r'db/etree_scrape.db') #make sure this is outside the loop called in the below function
    concert_folders = []

# two level deep folder enumeration for processing
    #parentofparents =r'M:/To_Tag'
    # parentofparents = r'/Users/rjl/Documents/GitHub/etree_tag/test'
    # parentlist = sorted([f.path.replace('\\','/') for f in os.scandir(parentofparents) if f.is_dir()])
    # for parentfolder in parentlist:
    #     if parentfolder.lower().endswith("fail"): #addl filtering, exclude if the folder name ends with fail
    #         continue
    #     concert_folders.extend(sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()]))

#single parent folder
    parentfolder = r'X:\Downloads\_FTP\gdead.9999.updates'
    concert_folders = sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()])

#if using a single folder, or specific folders use a python list of path(s):
#best for getting started and testing
    # concert_folders = [
    #        r"M:\To_Tag\gd1966\gd1966-xx.xx.136658.acidtest#3.sbd.mr.datflac1644"
    #  ]    
    #concert_folders must be a list of folders that contain folders. 
    #Don't pass without parent directory, it won't be good
    #TODO, add some type of check when scanning the first folder

    ConcertTagger.tag_shows(concert_folders, etreedb, config, clear_existing_tags=True)

    etreedb.close
    
    end_time = perf_counter()
    print(f"Runtime: {end_time - start_time:.4f} seconds")
    logging.info(f"Runtime: {end_time - start_time:.4f} seconds")
    
