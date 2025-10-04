from pathlib import Path
from mutagen.flac import FLAC
import logging
from sqliteetreedb import SQLiteEtreeDB, EtreeRecording
from losslessfiles import ffp
import re
from datetime import datetime
# from import_show_metadata import import_show_folders


class RecordingFolder:
    def __init__(self, concert_folder: str, etree_db: SQLiteEtreeDB | None = None):
        """
        Initialize the Concert for a given concert folder.

        Args:
            concert_folder (str): Path to the folder containing concert files.
            This folder should include one or more .flac files and may also contain:
                  - an info file (a .txt file with "info" in the name),
                  - a fingerprint file (with .ffp extension),
                  - a checksum file (with .st5 extension),
                  - and artwork (e.g. folder.jpg, cover.jpg, or front.jpg).
            etree_db (SQLiteEtreeDB | None): Optional database instance used for
                matching recordings. If not provided, ``_find_matching_recording``
                must be passed a database when called.
        """
        self.folder = Path(concert_folder)
        self.etree_db = etree_db
        if not self.folder.is_dir():
            logging.error(f"{concert_folder} is not a valid directory.")
            raise ValueError(f"{concert_folder} is not a valid directory.")
        self.foldershnid = self._parse_shnid(self.folder.name)
        self.musicfiles = [MusicFile(str(x)) for x in self.folder.glob("*.flac")]

        # identify optional companion files
        self.info_file = self._find_file_by_keyword(
            "txt", "info"
        ) or self._find_file_by_extension("txt")
        self.fingerprint_file = self._find_file_by_extension("ffp")
        self.st5_file = self._find_file_by_extension("st5")
        self.artwork_file = self._find_artwork()
        self.checksums = self._get_checksums(self.musicfiles)
        self.recordingtype = self._classify_folder(self.folder.name)

        logging.info(f"Found {len(self.musicfiles)} FLAC file(s) in {self.folder}")

    # def import_show_tags(self):
    #     """
    #     Import show folders into the database.
    #     This function processes each concert folder, checks for missing track titles,
    #     and attempts to tag the files if necessary. It logs any errors encountered
    #     during the process. If a folder is successfully tagged, it updates the database
    #     with the new track metadata.
    #     Args:
    #         concert_folders (list): List of concert folder paths to process.
    #         etree_db (SQLiteEtreeDB): Database connection object.
    #         config: Configuration object for the tagging process.
    #     Returns:
    #         successfully_imported (list): List of concert folders that were successfully imported to the database.
    #     """
    #     successfully_imported = []
    #     # existing_folders = []
    #     # try:
    #     #     with open("mismatched_folders.txt", "r", encoding="utf-8") as mismatchlogexisting:
    #     #         existing_mismatched_folders = mismatchlogexisting.readlines()
    #     # except FileNotFoundError:
    #     #     existing_mismatched_folders = []
    #     # with open("mismatched_folders.txt", "a", encoding="utf-8") as mismatchlog:
    #         for concert_folder in concert_folders:
    #             try:
    #                 show = ConcertTagger(concert_folder,config,etree_db, debug=False)
    #                 print(f'{show.etreerec.id=} {show.etreerec.md5key=} {show.folderpath=}')
    #                 tracks = show.etreerec.tracks
    #                 tracknames = [track.title for track in tracks]
    #                 #print(f'{tracknames=}')
    #                 if not tracknames:
    #                     tracks = [track.title for track in show.folder.musicfiles]
    #                     #for track in tracks:
    #                     #    print(f'{track}')
    #                     if None in tracks:
    #                         tagged = InfoFileTagger.tag_folder(show.folderpath)
    #                         if tagged:
    #                             print(f'Sucessfully tagged files in folder {concert_folder}')
    #                             show = ConcertTagger(concert_folder,config,etree_db)
    #                             tracks = [track.title for track in show.folder.musicfiles]
    #                         else:
    #                             error = f'Error tagging files in folder {concert_folder}'
    #                             print(error)
    #                             logging.error(error)
    #                             continue

    #                     if None in tracks:
    #                         missingtitlefiles = ', '.join([file.name for file in show.folder.musicfiles if file.title is None])
    #                         error = f'Error Processing folder {concert_folder}: missing track title(s) {missingtitlefiles}'
    #                         print(error)
    #                         logging.error(error)
    #                     else:
    #                         rows = show.build_show_inserts()
    #                         print(f"inserting {len(rows)} rows for {concert_folder}")
    #                         show.db.insert_track_metadata(show.etreerec.id, rows,False,show.etreerec.md5key, debug = True)
    #                         successfully_imported.append(concert_folder)
    #                 else:
    #                     existing_folders.append(concert_folder)
    #                     print(f"Matching tracknames exist for {concert_folder}")
    #             except Exception as e:
    #                 logging.error(f'Error Processing folder {concert_folder} {e}')
    #                 if concert_folder+'\n' not in existing_mismatched_folders:
    #                     mismatchlog.write(f"{concert_folder}\n")
    #     return successfully_imported, existing_folders

    def _classify_folder(self, folder_name: str) -> str:
        """
        Classify the folder_name based on various substring patterns, similar to a SQL CASE statement.
        Currently used for tagging shows.

        The matching is done on the lowercase version of folder_name.

        Returns:
            A classification string such as 'SBD', 'Studio', 'Ultramatrix', 'MTX', 'Pre-FM', 'FM', 'AUD', or 'DTS',
            or None if no pattern matches.
        """
        lower_folder = folder_name.lower()

        # Check in the following order:
        if "ultra" in lower_folder:
            return "Ultramatrix"
        elif (
            "sbd" in lower_folder
            or "bettyboard" in lower_folder
            or "sdb" in lower_folder
        ):
            return "SBD"
        elif "studio" in lower_folder:
            return "Studio"
        elif "rehear" in lower_folder:
            return "Rehearsal"
        elif "mtx" in lower_folder or "matrix" in lower_folder:
            return "MTX"
        elif "fob" in lower_folder:
            return "AUD"
        elif "pre" in lower_folder and "fm" in lower_folder:
            return "Pre-FM"
        elif "fm" in lower_folder:
            return "FM"
        elif any(
            x in lower_folder
            for x in [
                "aud",
                "nak",
                "senn",
                "akg",
                "sony",
                "beyer",
                "schoeps",
                "scheops",
                "schopes",
                "bk4011",
                "at835",
                "neumann",
                "shure",
                "ecm",
                "b&k",
                "pzm",
                "ec7",
                "sanken",
                "kmf4",
            ]
        ):
            return "AUD"
        elif "dts" in lower_folder:
            return "DTS"
        else:
            return None

    def build_track_inserts(self):
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
                file.name,
            )

            results.append(x)
        return results

    def _get_checksums(self, files: list):
        self.checksums = []
        for file in files:
            self.checksums.append(file.checksum)
        return self.checksums

    def _parse_shnid(self, input_str):
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
        parts = input_str.split(".")
        for part in parts:
            if part.isdigit():
                return int(part)
        return None

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

    def _find_matching_recording(
        self, db: SQLiteEtreeDB | None = None, debug: bool = False
    ):
        """Return an ``EtreeRecording`` matching this folder's checksums, if any."""
        if db is None:
            db = self.etree_db
        if db is None:
            raise ValueError("SQLiteEtreeDB instance required")

        if not self.checksums:
            return None

        matches, mismatch = db.get_local_checksum_matches(self.checksums)
        if debug:
            print(f"{self.checksums=}")
            print(f"{matches=}")
            print(f"{mismatch=}")

        checksum_pairs = set()

        def _find_matching_pairs(match_list):
            for shnid, md5key in match_list:
                if debug:
                    print(f"{shnid=}", f"{md5key=}")
                try:
                    rec = EtreeRecording(db, shnid, md5key)
                except Exception as e:
                    msg = f"Error encountered for {self.folder}: {e}"
                    if debug:
                        print(msg)
                    raise Exception(msg)
                if debug:
                    print(f"{rec.id=}", f"{rec.md5key=}", f"{rec.checksums=}")
                for sig in rec.checksums:
                    if set(sig.checksumlist) == set(self.checksums):
                        print(
                            f"Match found: {sig.filename} md5key={sig.id} shnid={sig.shnid}"
                        )
                        if rec.tracks:
                            return rec
                        checksum_pairs.add((sig.shnid, sig.id))
                        break

        if not mismatch:
            found = _find_matching_pairs(matches)
            if found is not None:
                return found

        result = None
        if not checksum_pairs:
            # attempt to find remote matches. If anything new is found, add it to the local db
            remote_matches = db.get_remote_checksum_matches(self.checksums)
            if remote_matches:
                matches, mismatch = db.get_local_checksum_matches(self.checksums)
                # if self.
                if not mismatch:
                    found = _find_matching_pairs(matches)
                    if found is not None:
                        return found
        for shnid, md5key in checksum_pairs:
            result = EtreeRecording(db, shnid, md5key)
            if self.foldershnid == result.id:
                print(f"Exact match found for shnid {result.id} in folder name")
                logging.info(f"Exact match found for shnid {result.id} in folder name")
                return result
            print(
                f"No EXACT MATCH found for shnid {self.foldershnid} using {result.id}"
            )
            logging.warn(
                f"No EXACT MATCH found for shnid {self.foldershnid} using {result.id}"
            )
        return result

    def _standardize_folder_year(self, etree_rec: EtreeRecording | None):
        """Validate and normalize the folder name using database info."""
        if not etree_rec or not etree_rec.artist_abbrev:
            return

        folder_name = self.folder.name
        abbr = etree_rec.artist_abbrev

        shnid = getattr(etree_rec, "id", None)
        db_date = getattr(etree_rec, "date", None)

        if not folder_name.lower().startswith(abbr.lower()):
            msg = f"Folder name {folder_name} does not start with {abbr}"
            print(msg)
            logging.error(msg)
            return

        parts = folder_name.split(".")
        first = parts[0]
        others = parts[1:]

        # Strip artist abbreviation
        remainder = first[len(abbr) :]

        # Handle year expansion
        m = re.match(r"(?P<year>\d{4})(?P<rest>.*)$", remainder)
        if m:
            year = m.group("year")
            after_year = m.group("rest")
        else:
            m2 = re.match(r"(?P<year>\d{2})(?P<rest>.*)$", remainder)
            if not m2:
                return
            year = datetime.strptime(m2.group("year"), "%y").strftime("%Y")
            after_year = m2.group("rest")

        # Ensure -XX-XX after year
        mdate = re.match(r"-(?P<month>..)-(?P<day>..)(?P<rest>.*)$", after_year)
        if mdate:
            month = mdate.group("month")
            day = mdate.group("day")
            after_date = mdate.group("rest")
        else:
            if db_date:
                month = db_date[5:7]
                day = db_date[8:10]
            else:
                month = "??"
                day = "??"
            after_date = after_year.lstrip("-")
            after_date = (
                f".{after_date}"
                if after_date and not after_date.startswith(".")
                else after_date
            )

        # Compare to DB date when numeric
        candidate_date = f"{year}-{month}-{day}"
        try:
            folder_dt = datetime.strptime(candidate_date, "%Y-%m-%d")
            db_dt = datetime.strptime(db_date, "%Y-%m-%d") if db_date else None
            if db_dt and folder_dt.date().isoformat() != db_dt.date().isoformat():
                month = db_date[5:7]
                day = db_date[8:10]
        except Exception:
            pass

        first = f"{abbr}{year}-{month}-{day}{after_date}"

        # Ensure shnid position
        if shnid is not None:
            shnid_str = str(shnid)
            others = [p for p in others if p != shnid_str]
            others.insert(0, shnid_str)

        new_name = ".".join([first] + others)
        while ".." in new_name:
            new_name = new_name.replace("..", ".")

        if new_name != folder_name:
            new_path = self.folder.with_name(new_name)
            try:
                self.folder.rename(new_path)
            except FileExistsError:
                logging.error(
                    f"Cannot rename {self.folder} to {new_path}: target exists"
                )
                return

            # Reinitialize to update all path-based attributes
            self.__init__(str(new_path), self.etree_db)

    def verify_fingerprint(self):
        """Verify FLAC files using an ffp checksum file.

        If ``self.fingerprint_file`` exists, it is read and used for
        verification. If not, a new fingerprint file is generated from
        ``self.musicfiles`` before verification.
        """
        if self.fingerprint_file and self.fingerprint_file.exists():
            ff = ffp(str(self.folder), self.fingerprint_file.name)
            ff.readffpfile()
        else:
            sigs = {m.name: m.checksum for m in self.musicfiles}
            fname = f"{self.folder.name}.ffp"
            ff = ffp(str(self.folder), fname, sigs)
            ff.SaveFfp()
            self.fingerprint_file = self.folder / fname
        ff.verify()
        return ff.result, ff.errors


class MusicFile:
    def __init__(self, path):
        self.path = path
        self.name = Path(path).name
        self.audio = FLAC(path)
        self.length = self.format_time_seconds_to_mins_seconds(self.audio.info.length)
        self.checksum = format(self.audio.info.md5_signature, "032x")
        self.disc = self.audio["discnumber"][0] if "discnumber" in self.audio else None
        self.tracknum = (
            self.audio["tracknumber"][0] if "tracknumber" in self.audio else None
        )
        self.title = self.audio["title"][0].strip() if "title" in self.audio else None

    def format_time_seconds_to_mins_seconds(self, seconds):
        seconds = int(seconds)
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes:02}:{remaining_seconds:02}"


# Example usage:
if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    # TODO: below is unimplemented for load to db so far, but will be used to pull entries into the database from files. Current code needs a cleanup and will be merged into this module
    concert_folder = r"X:\Downloads\_FTP\gdead.1982.project_missing\gd1982-09-12.7826.sbd.ladner.sbeok.flac16"
    etree_db = SQLiteEtreeDB()
    tagger = RecordingFolder(concert_folder, etree_db)
    rows = tagger.build_track_inserts()
    for row in rows:
        print(row)
