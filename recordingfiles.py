from pathlib import Path
from mutagen.flac import FLAC, Picture
import logging

class RecordingFolder:
    def __init__(self, concert_folder: str):
        """
        Initialize the Concert for a given concert folder.

        Args:
            concert_folder (str): Path to the folder containing concert files.
                This folder should include one or more .flac files and may also contain:
                  - an info file (a .txt file with "info" in the name),
                  - a fingerprint file (with .ffp extension),
                  - a checksum file (with .st5 extension),
                  - and artwork (e.g. folder.jpg, cover.jpg, or front.jpg).
        """
        self.folder = Path(concert_folder)
        if not self.folder.is_dir():
            raise ValueError(f"{concert_folder} is not a valid directory.")
        self.foldershnid = self._parse_shnid(self.folder.name)
        #self.flac_file_list = list(self.folder.glob("*.flac"))
        self.musicfiles =  [MusicFile(str(x)) for x in self.folder.glob("*.flac")]
        #self.load_flac_files()
        self.text_files = self.folder.glob("*.txt")
        self.fingerprint_files = self.folder.glob("*.ffp")
        self.st5_files = self.folder.glob("*.st5")
        self.checksums = self._get_checksums(self.musicfiles)
        self.recordingtype = self._classify_folder(self.folder.name)

      
        #self.artwork_file = self._find_artwork()

        logging.info(f"Found {len(self.musicfiles)} FLAC file(s) in {self.folder}")

    def _classify_folder(self,folder_name: str) -> str:
        """
        Classify the folder_name based on various substring patterns, similar to a SQL CASE statement.
        
        The matching is done on the lowercase version of folder_name.
        
        Returns:
            A classification string such as 'SBD', 'Studio', 'Ultramatrix', 'MTX', 'Pre-FM', 'FM', 'AUD', or 'DTS',
            or None if no pattern matches.
        """
        lower_folder = folder_name.lower()
        
        # Check in the following order:
        if 'ultra' in lower_folder:
            return 'Ultramatrix'
        elif 'sbd' in lower_folder or 'bettyboard' in lower_folder or 'sdb' in lower_folder:
            return 'SBD'
        elif 'studio' in lower_folder:
            return 'Studio'
        elif 'rehear' in lower_folder:
            return 'Rehearsal'        
        elif 'mtx' in lower_folder or 'matrix' in lower_folder:
            return 'MTX'
        elif 'fob' in lower_folder:
            return 'AUD'
        elif 'pre' in lower_folder and 'fm' in lower_folder:
            return 'Pre-FM'
        elif 'fm' in lower_folder:
            return 'FM'
        elif any(x in lower_folder for x in [
                'aud', 'nak', 'senn', 'akg', 'sony', 'beyer',
                'schoeps', 'scheops', 'schopes', 'bk4011', 'at835',
                'neumann', 'shure', 'ecm', 'b&k', 'pzm', 'ec7', 'sanken','kmf4']):
            return 'AUD'
        elif 'dts' in lower_folder:
            return 'DTS'
        else:
            return None

    def build_track_inserts (self):
        results = []
        for file in self.musicfiles:
            x = (
            file.disc,
            file.tracknum,
            file.title,
            file.checksum,
            file.audio.info.bits_per_sample,
            file.audio.info.sample_rate,
            file.length,
            file.audio.info.channels,
            file.name
            )

            results.append(x)
        return results

    def _get_checksums(self,files:list):
        self.checksums = []
        for file in files:
            self.checksums.append(file.checksum)
        return self.checksums

    def _parse_shnid(self,input_str):
        """
        Parses the input string to find the first sequence of characters between periods
        that is entirely numeric. Leading zeros are removed by converting the value to an integer.
        
        For example:
        "gd1980-04-28.0088858.fob.glassberg.motb.0040.flac16"
        will return:
        88858
        
        Parameters:
        input_str (str): The string to parse.
        
        Returns:
        int or None: The parsed shnid as an integer, or None if no numeric part is found.
        """
        parts = input_str.split('.')
        for part in parts:
            if part.isdigit():
                return int(part) 
        return None

    # def load_flac_files(self):
    #     """
    #     Populate self.flac_files with a mutagen FLAC object for each file in self.flac_file_list.
    #     Any file that cannot be loaded will be logged as an error.
    #     """
    #     self.flac_files = {}
    #     for file_path in self.flac_file_list:
    #         try:
    #             audio = FLAC(str(file_path))
    #             self.flac_files[file_path]=audio
    #             logging.info(f"Loaded FLAC file: {file_path}")
    #         except Exception as e:
    #             logging.error(f"Error loading FLAC file {file_path}: {e}")

    def _find_file_by_keyword(self, ext: str, keyword: str):
        """Return the first file with extension 'ext' whose name contains 'keyword'."""
        for file in self.folder.glob(f"*.{ext}"):
            if keyword.lower() in file.name.lower():
                return file
        return None

    def _find_file_by_extension(self, ext: str):
        """Return the first file found with the given extension."""
        for file in self.folder.glob(f"*.{ext}"):
            return file
        return None

    def _find_artwork(self):
        """
        Look for common artwork file names (e.g. folder.jpg, cover.jpg, front.jpg)
        in the concert folder.
        """
        possible_names = ["folder.jpg", "cover.jpg", "front.jpg"]
        for name in possible_names:
            candidate = self.folder / name
            if candidate.exists():
                return candidate
        return None

    def read_info(self) -> str:
        """Return the text from the info file, if available; else, return an empty string."""
        if self.info_file and self.info_file.exists():
            return self.info_file.read_text(encoding="utf-8")
        return ""

    def read_fingerprint(self) -> str:
        """Return the text from the fingerprint file, if available; else, return an empty string."""
        if self.fingerprint_file and self.fingerprint_file.exists():
            return self.fingerprint_file.read_text(encoding="utf-8")
        return ""

    def read_checksums(self) -> str:
        """Return the text from the checksum (.st5) file, if available; else, return an empty string."""
        if self.st5_file and self.st5_file.exists():
            return self.st5_file.read_text(encoding="utf-8")
        return ""

    # def tag_concert(self, tags: dict):
    #     """
    #     Apply the provided tags to all FLAC files in the concert folder.

    #     Args:
    #         tags (dict): A dictionary of tag key/value pairs (e.g., {"artist": "Bob Dylan", "album": "Live Concert 1994"}).
    #     """
    #     for file in self.flac_files:
    #         try:
    #             audio = FLAC(str(file))
    #             for key, value in tags.items():
    #                 audio[key] = value
    #             audio.save()
    #             logging.info(f"Tagged file: {file}")
    #         except Exception as e:
    #             logging.error(f"Error tagging file {file}: {e}")

    # def apply_tags(self, tags: dict, clear_all: bool = False, clear_tags: list = None, add_artwork: bool = False, clear_existing_artwork: bool = True):
    #     """
    #     Apply text tags and (optionally) artwork to all FLAC files in the concert folder,
    #     and save each file only once after all modifications are done.

    #     Args:
    #         tags (dict): Dictionary of tag key/value pairs to apply to each file.
    #         clear_all (bool): If True, remove all tags and embedded pictures before applying new tags.
    #         clear_tags (list): If provided and clear_all is False, a list of specific tag keys to remove.
    #         add_artwork (bool): If True, add artwork from self.artwork_file.
    #         clear_existing_artwork (bool): If True, remove any existing artwork before adding new artwork.
    #                                     If False, add artwork only if the file doesn't already have any.
    #     """

    #     for file in self.flac_files:
    #         try:
    #             audio = FLAC(str(file))

    #             # Clear tags as requested
    #             if clear_all:
    #                 audio.clear()          # Remove all textual tags
    #                 audio.clear_pictures() # Remove any embedded artwork
    #                 logging.info(f"Cleared all tags for {file}")
    #             elif clear_tags:
    #                 for tag in clear_tags:
    #                     if tag in audio:
    #                         del audio[tag]
    #                         logging.info(f"Cleared tag '{tag}' for {file}")

    #             # Apply new tags
    #             for key, value in tags.items():
    #                 audio[key] = value

    #             # Optionally add artwork
    #             if add_artwork and self.artwork_file:
    #                 try:
    #                     with open(self.artwork_file, "rb") as f:
    #                         image_data = f.read()
    #                     pic = Picture()
    #                     pic.type = 3  # Front cover
    #                     pic.mime = "image/jpeg"  # Adjust if needed
    #                     pic.data = image_data
    #                     if clear_existing_artwork:
    #                         audio.clear_pictures()
    #                         audio.add_picture(pic)
    #                         logging.info(f"Cleared and added artwork to {file}")
    #                     else:
    #                         if not audio.pictures:
    #                             audio.add_picture(pic)
    #                             logging.info(f"Added artwork to {file}")
    #                         else:
    #                             logging.info(f"Artwork already exists in {file}")
    #                 except Exception as art_e:
    #                     logging.error(f"Error adding artwork to {file}: {art_e}")

    #             # Save changes once per file after all modifications are done
    #             audio.save()
    #             logging.info(f"Saved file: {file}")

    #         except Exception as e:
    #             logging.error(f"Error processing file {file}: {e}")
    
class MusicFile:
    def __init__(self,path):
        self.path = path
        self.name = Path(path).name
        self.audio = FLAC(path)
        self.length = self.format_time_seconds_to_mins_seconds(self.audio.info.length)
        self.checksum = format(self.audio.info.md5_signature, '032x')
        self.disc = self.audio['discnumber'][0] if 'discnumber' in self.audio else None
        self.tracknum = self.audio['tracknumber'][0] if 'tracknumber' in self.audio else None
        self.title = self.audio['title'][0].strip() if 'title' in self.audio else None        
    def format_time_seconds_to_mins_seconds(self,seconds):
        seconds = int(seconds)
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes:02}:{remaining_seconds:02}"     


# Example usage:
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    # Replace with your concert folder path.
    #concert_folder = r"X:\Downloads\_FTP\gdead.1978.project_missing\gd1978-11-24.303.flac16"
    concert_folder = r"X:\Downloads\_FTP\gdead.1982.project_missing\gd1982-09-12.7826.sbd.ladner.sbeok.flac16"
    tagger = RecordingFolder(concert_folder)
    rows = tagger.build_track_inserts()
    for row in rows:
        print(row)
        

    # Optionally, print auxiliary file contents.
"""   
    print("Info file contents:")
    print(tagger.read_info())
    print("\nFingerprint file contents:")
    print(tagger.read_fingerprint())
    print("\nChecksum file contents:")
    print(tagger.read_checksums())
""" 
    # Define some tags to apply.
"""
    tags_to_apply = {
        "artist": "Bob Dylan",
        "album": "Live at the Palace Theater",
        "date": "1994-10-16",
        "location": "Palace Theater"
    }
    tagger.tag_concert(tags_to_apply)
    tagger.tag_artwork()
    print("Tagging complete.")
"""    
