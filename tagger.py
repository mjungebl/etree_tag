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
        """    
        # Load the configuration from your flac_config.toml file.
        config = load_config("flac_config.toml")

        # Extract values from the [preferences] section.
        year_format = config["preferences"]["year_format"]
        segue_string = config["preferences"]["segue_string"]
        soundboard_abbrev = config["preferences"]["soundboard_abbrev"]
        aud_abbrev = config["preferences"]["aud_abbrev"]
        matrix_abbrev = config["preferences"]["matrix_abbrev"]
        ultramatrix_abbrev = config["preferences"]["ultramatrix_abbrev"]

        # Extract values from the [album_tag] section.
        include_bitrate = config["album_tag"]["include_bitrate"]
        include_bitrate_not16_only = config["album_tag"]["include_bitrate_not16_only"]
        include_venue = config["album_tag"]["include_venue"]
        include_city = config["album_tag"]["include_city"]
        order = config["album_tag"]["order"]
        prefix = config["album_tag"]["prefix"]
        suffix = config["album_tag"]["suffix"]

        # Extract values from the [cover] section.
        artwork_folders = config["cover"]["artwork_folders"]
        defaultimage_path = config["cover"]["defaultimage_path"]
        """
    except Exception as e:
        print(f"Error loading configuration: {e}")
        raise    




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
        if self.NoMatch == False:
            try:
                self.artworkpath = self._find_artwork('gd',self.etreerec.date)
            except Exception as e:
                print(f'Exception: {e} for {self.folderpath.as_posix()}')
                #raise Exception(f'ERROR:{e}')
                self.errormsg = f'No Matching recording found in database for folder {self.folderpath.as_posix()}'
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

    def tag_artwork(self, clear_existing: bool = False, num_threads: int = 5):
        """
        Add artwork to all FLAC files using multithreading.

        Args:
            clear_existing (bool): If True, remove any existing artwork before adding the new image.
                                    If False, add artwork only if no artwork is present.
            num_threads (int, optional): Number of threads to use. Defaults to os.cpu_count()-1.
        """
        if not self.artworkpath:
            logging.info("No artwork file found to tag.")
            return

        artwork_path_str = str(self.artworkpath)
        
        dest_file = os.path.join(self.folderpath.as_posix(), "folder.jpg")
        if not os.path.exists(dest_file):
            try:
                shutil.copy2(artwork_path_str, dest_file)
                logging.info(f"Copied artwork to {dest_file}")
            except Exception as e:
                logging.error(f"Error copying artwork: {e}")
        else:
            logging.info(f"Artwork already exists at {dest_file}")        
        # Build argument list using the files from your folder's musicfiles attribute.
        args_list = [
            (file.path, file.name, artwork_path_str, clear_existing)
            for file in self.folder.musicfiles
        ]

        if num_threads is None:
            cpu_count = os.cpu_count() or 1
            num_threads = max(1, cpu_count - 1)
        tickers = len(args_list)
        pbar = tqdm(total=tickers, desc='Tagging')
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {executor.submit(_tag_artwork_for_file_thread, args): args[1] for args in args_list}
            for future in as_completed(futures):
                file_name = futures[future]
                pbar.update(n=1)
                try:
                    name, success, error = future.result()
                except Exception as e:
                    name = file_name
                    success = False
                    error = str(e)
                #if success:
                #    print(f"[OK]   {name}")
                #else:
                #    print(f"[FAIL] {name} - {error}")

    def tag_album(self, clear_existing: bool = True):
        #TODO customise this string (separate function?)
        #print(f'{self.etreerec.date=}')
        album = f'{self.etreerec.date} {self.etreerec.etreevenue} {'('+self.folder.recordingtype+') ' if self.folder.recordingtype else ''}{'['+str(self.folder.musicfiles[0].audio.info.bits_per_sample)+'-'+
                                                                   str(self.folder.musicfiles[0].audio.info.sample_rate).rstrip('0')+
                                                                   '] ' if self.folder.musicfiles and str(self.folder.musicfiles[0].audio.info.bits_per_sample) != '16' else ''}{'('+str(self.etreerec.id)+')'}'
        print(f'Tagging {album} in {self.folderpath.as_posix()}')
        if not self.etreerec.tracks:
            logging.error(f'Unable to tag tracks for folder: {self.folderpath.as_posix()}')
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
                    if self.etreerec.tracks:
                        song_info =self.etreerec.get_track_by_checksum(file.checksum)
                        if song_info:
                        #print(f'Song details: {song_info.title} {song_info.disc} {song_info.tracknum}')
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
    
    def tag_shows(concert_folders:list, etree_db:SQLiteEtreeDB, config):
        folder_count = len(concert_folders)
        currentcount = 0
        
        print(f"Processing tags for {folder_count} folders.")
        for concert_folder in concert_folders:
            currentcount = currentcount + 1
            print("------------------------------------------------------------------------------")
            print(f"Processing {currentcount}/{folder_count} tagging: {Path(concert_folder).name}")
            try:
                tagger = ConcertTagger(concert_folder, config, etree_db)
                if not tagger.errormsg:
                    tagger.tag_album()
                    tagger.tag_artwork()
            except Exception as e:
                logging.error(f'Error Processing folder {concert_folder}')

# Example usage:
if __name__ == "__main__":
    from time import perf_counter
    start_time = perf_counter()
    logfilename = 'tagalog.log' 
    logging.basicConfig(filename=logfilename,level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    config_file = os.path.join(os.path.dirname(__file__),"config.toml")
    config = load_config(config_file)
    #config = load_config(config_file)
    
    #concert_folders = [
    #    r"X:\Downloads\_FTP\gdead.1991.project\gd1991-05-12.31962.sbd.miller.sbeok.t-flac16"
    #]
    
    parentfolderpath = r'M:\To_Tag\gd1983'
    #parentfolderpath = r'X:\Downloads\_FTP\gdead.1984.project'
    #parentfolderpath = r'X:\Downloads\_FTP\gdead.0000.FIXME'
    parentfolder = Path(parentfolderpath).as_posix()
    #concert_folders must be a list of folders that contain folders. Don't pass wht parent directory, it won't be good
    #TODO, add some type of check when scanning the first folder
    #take only one level of directories from the parent folder
    
    concert_folders = sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()]) 
    #concert_folders = [r'Z:\Music\Grateful Dead\gd1991\gd1991-10-30.139275.sbd.cm.miller.flac24']
    etreedb = SQLiteEtreeDB() #make sure this is outside the loop
    ConcertTagger.tag_shows(concert_folders,etreedb,config)
    


    etreedb.close
    
    end_time = perf_counter()
    print(f"Runtime: {end_time - start_time:.4f} seconds")
    logging.info(f"Runtime: {end_time - start_time:.4f} seconds")
    
        
                    


