import sqlite3
import logging
import datetime
import csv
import os
import shutil
import zipfile

class SQLiteEtreeDB:
    def __init__(self, db_path="db/etree_tag_db.db", log_level=logging.ERROR):
        """Initialize database connection and set up logging."""
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.initialize_eventdb()
        self.translations = self.build_title_transformations_dict()
        # Set up logging
        logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
        
        # Initialize tables
        

    def initialize_eventdb(self):
        """Creates necessary tables if they do not exist."""
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS signatures (
                    shnid INTEGER,
                    md5key INTEGER,
                    base_filename TEXT,
                    file_extension TEXT,
                    audio_checksum TEXT,
                    --file_type TEXT,
                    PRIMARY KEY (shnid, md5key, base_filename,file_extension)
                )
            """)
            self.cursor.execute('SELECT COUNT(*) FROM signatures;')
            count = self.cursor.fetchone()[0]
            if count == 0:
                with open('db/csv/signatures.csv', 'r', newline='', encoding="utf-8") as csvfile:
                    reader = csv.DictReader(csvfile)  # Uses the first row as headers
                    rows = []
                    for row in reader:
                        # Adjust the keys if necessary to match your table's columns
                        rows.append((row['shnid'], row['md5key'], row['base_filename'], row['file_extension'], row['audio_checksum']))
                    self.cursor.executemany('INSERT INTO signatures (shnid,md5key,base_filename,file_extension,audio_checksum) VALUES (?, ?, ?, ?, ?)', rows)
                        #self.conn.commit()

            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audio_checksum ON signatures(audio_checksum)
            """)
                          
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS shnlist (
                    shnid INTEGER PRIMARY KEY,
                    Date TEXT,
                    VenueSource TEXT,
                    CircDateAddedSource TEXT,
                    ChecksumsSource TEXT,
                    Source TEXT,
                    artist_id INTEGER,
                    Venue TEXT,
                    City TEXT
                )
            """)
            self.cursor.execute('SELECT COUNT(*) FROM shnlist;')
            count = self.cursor.fetchone()[0]
            if count == 0:
                with open('db/csv/shnlist.csv', 'r', newline='', encoding="utf-8") as csvfile:
                    reader = csv.DictReader(csvfile)  # Uses the first row as headers
                    rows = []
                    for row in reader:
                        # Adjust the keys if necessary to match your table's columns
                        rows.append((row['shnid'], row['Date'], row['VenueSource'], row['CircDateAddedSource'], row['ChecksumsSource'], row['Source'], row['artist_id'], row['Venue'], row['City']))
                    self.cursor.executemany('INSERT INTO shnlist (shnid,Date,VenueSource,CircDateAddedSource,ChecksumsSource,Source,artist_id,Venue,City) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)
                        #self.conn.commit()

            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS title_transformations (
                    title       TEXT,
                    title_clean TEXT,
                    gazinta     TEXT
                )
            """)

            self.cursor.execute('SELECT COUNT(*) FROM title_transformations;')
            count = self.cursor.fetchone()[0]            
            if count == 0:
                with open('db/csv/title_transformations.csv', 'r', newline='', encoding="utf-8") as csvfile:
                    reader = csv.DictReader(csvfile)  # Uses the first row as headers
                    rows = []
                    for row in reader:
                        # Adjust the keys if necessary to match your table's columns
                        rows.append((row['title'], row['title_clean'], row['gazinta']))
                    self.cursor.executemany('INSERT INTO title_transformations (title,title_clean,gazinta) VALUES (?, ?, ?)', rows)
                        #self.conn.commit()

            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS artists (
                    artistid INTEGER PRIMARY KEY,
                    ArtistName TEXT UNIQUE ON CONFLICT IGNORE
                )
            """)

            # Insert predefined artists, no need for a csv yet
            artists_data = [
                (2, 'Grateful Dead'),
                (4, 'Phish'),
                (12, 'Garcia'),
                (847,'Grateful Dead Compilations'),
                (28494,'Grateful Dead Interviews'),
                (8515,'Pigpen')
            ]
            self.cursor.executemany("INSERT OR REPLACE INTO artists (artistid, ArtistName) VALUES (?, ?);", artists_data)


            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS track_metadata (
                    shnid INTEGER,
                    disc_number TEXT,
                    track_number TEXT,
                    title TEXT,
                    fingerprint TEXT,
                    bit_depth TEXT,
                    frequency TEXT,
                    length TEXT,
                    channels TEXT,
                    filename TEXT,
                    title_clean TEXT,
                    gazinta TEXT,
                    md5key INTEGER
                )
            """)
            self.cursor.execute('SELECT COUNT(*) FROM track_metadata;')
            count = self.cursor.fetchone()[0]
            if count == 0:
                with open('db/csv/track_metadata.csv', 'r', newline='', encoding="utf-8") as csvfile:
                    reader = csv.DictReader(csvfile)  # Uses the first row as headers
                    rows = []
                    for row in reader:
                        # Adjust the keys if necessary to match your table's columns
                        rows.append((row['shnid'], row['disc_number'], row['track_number'], row['title'], row['fingerprint'], row['bit_depth'], row['frequency'], row['length'], row['channels'], row['filename'], row['title_clean'], row['gazinta'], row['md5key']))
                    self.cursor.executemany('INSERT INTO track_metadata (shnid,disc_number,track_number,title,fingerprint,bit_depth,frequency,length,channels,filename,title_clean,gazinta,md5key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)
                        #self.conn.commit()

            # Create an index on shnid if it doesn't exist.
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_shnid ON track_metadata (shnid)")
            
            # Create an index on fingerprint if it doesn't exist.
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprint ON track_metadata (fingerprint)")
            

            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS checksum_files (
                    md5key INTEGER PRIMARY KEY,
                    shnid INTEGER,
                    label TEXT,
                    filename TEXT
                )
            """)

            self.cursor.execute('SELECT COUNT(*) FROM checksum_files;')
            count = self.cursor.fetchone()[0]
            if count == 0:
                with open('db/csv/checksum_files.csv', 'r', newline='', encoding="utf-8") as csvfile:
                    reader = csv.DictReader(csvfile)  # Uses the first row as headers
                    rows = []
                    for row in reader:
                        # Adjust the keys if necessary to match your table's columns
                        rows.append((row['md5key'], row['shnid'], row['label'], row['filename']))
                    self.cursor.executemany('INSERT INTO checksum_files (md5key,shnid,label,filename) VALUES (?, ?, ?, ?)', rows)
                        #self.conn.commit()

            # Create an index on shnid for faster lookups.
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_checksum_files_shnid ON checksum_files (shnid)")         
            
            #no need to insert data here. This is used as a log for importing. 
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS folder_shnid_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shnid INTEGER,
                    folder_name TEXT,
                    check_date TEXT  -- We'll store the timestamp here in ISO8601 format
                )
            """)            
            self.conn.commit()

        except sqlite3.Error as e:
            logging.error(f"SQLite error during initialization: {e}")

    def insert_folder_shnid_log(self, shnid,folder_name):
        """
        Inserts a single record into the folder_shnid_log table.
        
        Before inserting, any existing record with the same md5key is deleted (full replace).
        
        Args:
            record (tuple): A tuple in the form (md5key, shnid, label, filename)
                            where md5key and shnid are integers, and label and filename are text.
        """
        now = datetime.datetime.now()
        timestamp = now.isoformat(sep=' ', timespec='seconds')  
        try:
            # Insert the new record.
            self.cursor.execute ("""
                INSERT INTO folder_shnid_log (shnid, folder_name, check_date)
                VALUES (?, ?, ?)
            """, (shnid,folder_name, timestamp))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error inserting folder_shnid_log record {shnid, folder_name,timestamp}: {e}")
            self.conn.rollback()
    def store_signatures(self, records):
        """Stores a list of signature records into the 'signatures' table."""
        try:
            md5key = records[0][1]
            self.cursor.execute("DELETE FROM signatures WHERE md5key = ?", (md5key,))
            self.cursor.executemany("""
                INSERT INTO signatures 
                (shnid, md5key, base_filename, file_extension, audio_checksum)
                VALUES (?, ?, ?, ?, ?)
            """, records)
            self.conn.commit()

        except sqlite3.Error as e:
            logging.error(f"SQLite error in store_signatures: {e}")

    # def store_artist_events(self, records):
    #     """Stores or updates artist event records in 'shnlist' table."""
    #     try:
    #         for row in records:
    #             shnid = int(row[5])
    #             self.cursor.execute("""
    #                 INSERT INTO shnlist (Date, VenueSource, CircDateAddedSource, ChecksumsSource, Source, shnid,artist_id)
    #                 VALUES (?, ?, ?, ?, ?, ?, ?)
    #                 ON CONFLICT(shnid) DO UPDATE SET
    #                     Date=excluded.Date,
    #                     VenueSource=excluded.VenueSource,
    #                     CircDateAddedSource=excluded.CircDateAddedSource,
    #                     ChecksumsSource=excluded.ChecksumsSource,
    #                     Source=excluded.Source,
    #                     artist_id=excluded.artist_id
    #             """, row)
    #             logging.info(f"Added Shnid: {shnid} to database")
    #         self.conn.commit()

    #     except sqlite3.Error as e:
    #         logging.error(f"SQLite error in store_artist_events: {e}")

    def store_artist_events(self, records):
        """Stores or updates artist event records in 'shnlist' table."""
        shnid = None
        try:
            for row in records:
                shnid = int(row[5])
                venuesource = row[1]
                if venuesource:
                    # Split the VenueSource by commas and remove extra whitespace
                    parts = [part.strip() for part in venuesource.split(',')]
                    if len(parts) >= 2:
                        # Last two elements are considered as City
                        city = ', '.join(parts[-2:])
                        # Everything before the last two elements is considered as Venue
                        venue = ', '.join(parts[:-2])
                    else:
                        # If there's less than 2 parts, use the entire string as Venue
                        venue = venuesource
                        city = ""
                row.append(venue)
                row.append(city)                 
                self.cursor.execute("""
                    INSERT INTO shnlist (Date, VenueSource, CircDateAddedSource, ChecksumsSource, Source, shnid,artist_id,Venue,City)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(shnid) DO UPDATE SET
                        Date=excluded.Date,
                        VenueSource=excluded.VenueSource,
                        CircDateAddedSource=excluded.CircDateAddedSource,
                        ChecksumsSource=excluded.ChecksumsSource,
                        Source=excluded.Source,
                        artist_id=excluded.artist_id,
                        Venue=excluded.Venue,
                        City=excluded.City
                """, row)
                if shnid:
                    logging.info(f"Added Shnid: {shnid} to database")
                else:
                    logging.error(f"No shnid found in records")                
            self.conn.commit()

        except sqlite3.Error as e:
            logging.error(f"SQLite error in store_artist_events: {e}")


    def get_shnid_info(self, shnid):
        """Retrieves a formatted string containing event info based on shnid."""
        try:
            self.cursor.execute("SELECT Date, VenueSource FROM shnlist WHERE shnid = ?", (shnid,))
            row = self.cursor.fetchone()
            return f"{row[0]} {row[1]} ({shnid})" if row else None

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_shnid_info: {e}")
            return None

    def get_source_by_shnid(self, shnid):
        """Retrieves the Source field for the given shnid."""
        try:
            self.cursor.execute("SELECT Source FROM shnlist WHERE shnid = ?", (shnid,))
            row = self.cursor.fetchone()
            return row[0] if row else None

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_source_by_shnid: {e}")
            return None

    def get_shnid_details(self, shnid):
        """
            Returns a tuple containing (Date,VenueSource,Source,artist_id,Venue, City) for a given shnid
        """
        try:
            self.cursor.execute("SELECT Date,VenueSource,Source,artist_id,Venue, City FROM shnlist WHERE shnid = ?", (shnid,))
            row = self.cursor.fetchone()
            return row if row else None

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_source_by_shnid: {e}")
            return None        

    def get_signatures_by_md5key(self, md5key):
        """Retrieves all records from the 'signatures' table for the given shnid."""
        try:
            self.cursor.execute("SELECT * FROM signatures WHERE shnid = ?", (md5key,))
            return self.cursor.fetchall()

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_records_by_shnid: {e}")
            return []

    def get_checksums_only_by_md5key(self, md5key):
        """Retrieves all records from the 'signatures' table for the given shnid."""
        try:
            self.cursor.execute("SELECT audio_checksum FROM signatures WHERE md5key = ?", (md5key,))
            return [x[0] for x in self.cursor.fetchall()]

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_records_by_shnid: {e}")
            return []

    def get_ffp_record_by_checksum(self, checksum):
        """Retrieves a record from 'signatures' table where file type is 'ffp' and checksum matches."""
        try:
            self.cursor.execute("""
                SELECT * FROM signatures WHERE audio_checksum = ? LIMIT 1
            """, (checksum,))
            return self.cursor.fetchone()

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_ffp_record_by_checksum: {e}")
            return None

    def get_ffp_shnids_checksum(self, checksum):
        """Retrieves records from 'signatures' table where checksum matches.
        args:
            checksum (str): The checksum to search for.
        Returns:
            list: A list of tuples [(shnid, md5key),].
        """
        try:
            self.cursor.execute("""
                SELECT shnid,md5key FROM signatures WHERE audio_checksum = ?
            """, (checksum,))
            return self.cursor.fetchall()

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_ffp_record_by_checksum: {e}")
            return None

    def get_existing_events(self):
        """Retrieves all existing shnids in the 'shnlist' table as a set."""
        try:
            self.cursor.execute("SELECT shnid FROM shnlist;")
            return {row[0] for row in self.cursor.fetchall()}

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_existing_events: {e}")
            return set()

    def close(self):
        """Closes the database connection."""
        self.conn.close()

    def get_artists_dict(self):
        """
        Retrieves all records from the 'artists' table and returns them as a dictionary,
        where the key is the ArtistName and the value is the artistid.

        Returns:
            dict: A dictionary mapping ArtistName to artistid.
        """
        try:
            self.cursor.execute("SELECT artistid, ArtistName FROM artists;")
            records = self.cursor.fetchall()
            return {artist_name: artist_id for artist_id, artist_name in records}

        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_artists_dict: {e}")
            return {}

    def get_artist_name(self,artist_id):
        """
        Retrieves all records from the 'artists' table and returns them as a dictionary,
        where the key is the ArtistName and the value is the artistid.

        Returns:
            dict: A dictionary mapping ArtistName to artistid.
        """
        try:
            self.cursor.execute("""SELECT ArtistName FROM artists where artistid = ?;""",(artist_id,))
            artistname = self.cursor.fetchone()
            return artistname[0] if artistname else None
        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_artists_dict: {e}")
            return {}


    def clean_title_field(self,title):
        """
        Clean the title string and derive the title_clean and gazinta fields.
        
        The cleaning logic follows these steps:
        1. Remove all carriage returns (\r) and linefeeds (\n) from the title.
        2. Trim whitespace from both ends.
        3. If the resulting string ends with ' ->', remove those last 3 characters and set gazinta to 'T'.
            Else if it ends with '->', remove the last 2 characters and set gazinta to 'T'.
            Else if it ends with ' >', remove the last 2 characters and set gazinta to 'T'.
            Else if it ends with '>', remove the last character and set gazinta to 'T'.
        4. If the cleaned title starts with '*', remove all '*' and then append a single '*' to the end.
        5. If the cleaned title starts with '/' but not with '//', then prepend an extra '/' (i.e. replace the first character with '//').
        6. Trim whitespace again.
        7. If the cleaned title starts with 'E: ' (i.e. the first 3 characters are "E: " in SQL, so in Python title[0:3]=="E: "), remove them and left‐trim the result.
        
        Returns a tuple (title_clean, gazinta). If title is None, both are returned as None.
        """
        if title is None:
            return None, None

        cleaned, gazinta = self.translations.get(title,(None,None))
        if cleaned:
            return cleaned, gazinta
        # Remove carriage returns and linefeeds, then trim whitespace.
        cleaned = title.replace('\r', '').replace('\n', '').strip()
        gazinta = None

        # Check ending tokens and remove them, setting gazinta to 'T' when appropriate.
        if cleaned.endswith(' ->'):
            cleaned = cleaned[:-3]
            gazinta = 'T'
        elif cleaned.endswith('->'):
            cleaned = cleaned[:-2]
            gazinta = 'T'
        elif cleaned.endswith(' >'):
            cleaned = cleaned[:-2]
            gazinta = 'T'
        elif cleaned.endswith('>'):
            cleaned = cleaned[:-1]
            gazinta = 'T'

        # If the string starts with '*', remove all '*' and then append one.
        if cleaned.startswith('*'):
            cleaned = cleaned.replace('*', '') + '*'

        # If the string starts with '/' but not with '//', prepend an extra '/'.
        if cleaned.startswith('/') and not cleaned.startswith('//'):
            cleaned = '//' + cleaned[1:]

        # Trim whitespace again.
        cleaned = cleaned.strip()

        # If the cleaned title starts with 'E: ', remove those first 3 characters and then trim.
        if cleaned.startswith("E: "):
            cleaned = cleaned[3:].lstrip()

        return cleaned, gazinta

    def insert_track_metadata(self, shnid, records, overwrite=False, md5key:int=None, debug = False):
        """
        Inserts a list of track_metadata records for the given shnid.

        If overwrite is True, the function performs a full replace:
        1. It deletes all existing records with the specified shnid.
        2. It inserts the new list of tuples.

        If overwrite is False, the function first checks whether any rows exist for the given shnid.
        If rows exist, it does not update (i.e., it skips deletion and insertion).

        Each record in `records` should be a tuple with the following fields:
        (shnid, disc_number, track_number, title, fingerprint, bit_depth, frequency, length, channels, filename)

        Before inserting, a helper function is called to derive two additional fields:
        - title_clean: the cleaned version of title (with CR/LF removed and other transformations)
        - gazinta: a flag (set to 'T' if one of the rules applies)

        The final insert will have 12 fields:
        (shnid, disc_number, track_number, title, fingerprint, bit_depth, frequency, length, channels, filename, title_clean, gazinta)

        Args:
        shnid (int): The shnid to replace records for.
        records (list of tuple): A list of track_metadata records.
        overwrite (bool, optional): If True, overwrite any existing records. Defaults to False.
        """
        if debug:
            print(f"shnid: {shnid} md5key: {md5key} overwrite: {overwrite}")
        col = "md5key" if md5key is not None else "shnid"
        value = md5key if md5key is not None else shnid        
        try:
            if not overwrite:
                # Check if any records exist for the given shnid.
                self.cursor.execute(f"SELECT 1 FROM track_metadata WHERE {col} = ?", (value,))
                if self.cursor.fetchone() is not None:
                    # Records already exist for this shnid, so we skip the update.
                    logging.warning(f"Records for {col} {value} already exist. Skipping update.")
                    return
            else:
                # Delete existing records for the given shnid.
                self.cursor.execute(f"DELETE FROM track_metadata WHERE {col} = ?", (value,))

            # Transform each record by cleaning the title field and appending title_clean and gazinta.
            new_records = []
            for rec in records:
                # Unpack original record fields
                # (shnid, disc_number, track_number, title, fingerprint, bit_depth, frequency, length, channels, filename)
                shnid_val, disc_number, track_number, title, fingerprint, bit_depth, frequency, length_val, channels, filename = rec
                title_clean, gazinta = self.clean_title_field(title)
                if md5key is None:
                    new_record = (shnid_val, disc_number, track_number, title, fingerprint, bit_depth, frequency, length_val, channels, filename, title_clean, gazinta)
                else:
                    new_record = (shnid_val, disc_number, track_number, title, fingerprint, bit_depth, frequency, length_val, channels, filename, title_clean, gazinta, md5key)
                new_records.append(new_record)
            if debug:
                print(f"new_records: {new_records}")
            # Insert the new records with the new fields.
            insert_sql = f"""
                INSERT INTO track_metadata (
                    shnid, disc_number, track_number, title, fingerprint,
                    bit_depth, frequency, length, channels, filename,
                    title_clean, gazinta {", md5key)" if md5key is not None else ")"} 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?{", ?)" if md5key is not None else ")"}
            """
            if debug:
                print(f"insert_sql: {insert_sql}")
            self.cursor.executemany(insert_sql, new_records)
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error inserting track metadata for shnid {shnid}: {e}")
            self.conn.rollback()


    def get_track_metadata(self, shnid:int, md5key:int=None):
        """
        Retrieves all track_metadata records for the given shnid.
        
        Args:
        shnid (int): The shnid whose records you want to retrieve.
        md5key (int, optional): If provided, retrieves records for this md5key instead of shnid.
        If both are provided, md5key takes precedence.
        
        Returns:
        list of tuples: Each tuple corresponds to a record with the following fields:
            (shnid, disc_number, track_number, title, fingerprint, bit_depth, frequency, length, channels, filename, md5key, title_clean, gazinta)
        """
        # try:
        #     self.cursor.execute("""
        #         SELECT shnid, disc_number, track_number, title, fingerprint, bit_depth, frequency, length, channels, filename, md5key, title_clean, gazinta
        #         FROM track_metadata
        #         WHERE shnid = ?
        #     """, (shnid,)) 
            # rows = self.cursor.fetchall()
        try:
            # If md5key is provided, use it to filter the query.
            col = "md5key" if md5key is not None else "shnid"
            value = md5key if md5key is not None else shnid

            query = f"""
                SELECT shnid, disc_number, track_number, title, fingerprint, bit_depth, frequency, length, channels, filename, md5key, title_clean, gazinta
                FROM track_metadata
                WHERE {col} = ?
            """
            self.cursor.execute(query, (value,))     
            rows = self.cursor.fetchall()       
            return rows
        except Exception as e:
            logging.error(f"Error retrieving track metadata for shnid {shnid}: {e}")
            return []


    def insert_checksum_file(self, record):
        """
        Inserts a single record into the checksum_files table.
        
        Before inserting, any existing record with the same md5key is deleted (full replace).
        
        Args:
            record (tuple): A tuple in the form (md5key, shnid, label, filename)
                            where md5key and shnid are integers, and label and filename are text.
        """
        try:
            md5key = record[0]
            # Delete any existing record with the same md5key.
            self.cursor.execute("DELETE FROM checksum_files WHERE md5key = ?", (md5key,))
            
            # Insert the new record.
            insert_sql = """
                INSERT INTO checksum_files (md5key, shnid, label, filename)
                VALUES (?, ?, ?, ?)
            """
            self.cursor.execute(insert_sql, record)
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error inserting checksum_files record {record}: {e}")
            self.conn.rollback()


    def get_checksum_files(self, shnid:int,md5key:int=None):
        """
        Retrieves all records from the checksum_files table for the given shnid or md5key. If both are provided, md5key takes precedence.
        Args:
            shnid (int): The shnid for which to retrieve the records.
            md5key (int, optional): If provided, retrieves records for this md5key instead of shnid.
        Returns:
            list of tuples: Each tuple is of the form (md5key, shnid, label, filename)
                            If an error occurs, an empty list is returned.
        """
        col = "md5key" if md5key is not None else "shnid"
        value = md5key if md5key is not None else shnid
        query = f"""
            SELECT md5key, shnid, label, filename
            FROM checksum_files
            WHERE {col} = ?
        """                
        try:
            # self.cursor.execute("""
            #     SELECT md5key, shnid, label, filename
            #     FROM checksum_files
            #     WHERE shnid = ?
            # """, (shnid,))
            self.cursor.execute(query, (value,))
            records = self.cursor.fetchall()
            return records
        except Exception as e:
            logging.error(f"Error retrieving checksum_files for shnid {shnid}: {e}")
            return []

    def get_checksum_file(self, md5key):
        """
        Retrieves a record from the checksum_files table for the given md5key.
        
        Args:
            md5key (int): The md5key for which to retrieve the record.
        
        Returns:
            tuple: (md5key, shnid, label, filename)
                            If an error occurs, None is returned.
        """
        try:
            self.cursor.execute("""
                SELECT md5key, shnid, label, filename
                FROM checksum_files
                WHERE md5key = ?
            """, (md5key,))
            records = self.cursor.fetchone()
            return records
        except Exception as e:
            logging.error(f"Error retrieving checksum_files for shnid {md5key}: {e}")
            return None


    def parse_venuesource(self, overwrite=False):
        """
        Parses the VenueSource field, extracting Venue and City information.
        Adds Venue and City columns if they are missing.

        :param overwrite: If True, updates all records. If False, only updates where Venue and City are NULL.
        """
        try:
            # Ensure Venue and City columns exist
            self.cursor.execute("""
                PRAGMA table_info(shnlist)
            """)
            columns = {row[1] for row in self.cursor.fetchall()}
            
            if "Venue" not in columns:
                self.cursor.execute("ALTER TABLE shnlist ADD COLUMN Venue TEXT")
            if "City" not in columns:
                self.cursor.execute("ALTER TABLE shnlist ADD COLUMN City TEXT")
            
            # Define condition based on the overwrite flag
            condition = "" if overwrite else "WHERE Venue IS NULL AND City IS NULL"
            
            # Fetch records that need to be updated
            self.cursor.execute(f"SELECT shnid, VenueSource FROM shnlist {condition}")
            rows = self.cursor.fetchall()
            
            for shnid, venuesource in rows:
                if venuesource:
                    # Split the VenueSource by commas and remove extra whitespace
                    parts = [part.strip() for part in venuesource.split(',')]
                    if len(parts) >= 2:
                        # Last two elements are considered as City
                        city = ', '.join(parts[-2:])
                        # Everything before the last two elements is considered as Venue
                        venue = ', '.join(parts[:-2])
                    else:
                        # If there's less than 2 parts, use the entire string as Venue
                        venue = venuesource
                        city = ""
                    
                    # Update the record with parsed Venue and City values
                    self.cursor.execute("""
                        UPDATE shnlist
                        SET Venue = ?, City = ?
                        WHERE shnid = ?
                    """, (venue, city, shnid))
            
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error processing records: {e}")
            self.conn.rollback()
            raise


    def build_title_transformations_dict(self):
        """
        Args:
            N/A
            
        Returns:
            dict: A dictionary with title as key and (title_clean, gazinta) as value.
        """
        results = {}
        try:        
        
            self.cursor.execute("SELECT title, title_clean, gazinta FROM title_transformations where title <> title_clean;")
        

            for row in self.cursor.fetchall():
                title, title_clean, gazinta = row
                results[title] = (title_clean, gazinta)
        except Exception as e:
            print(f"build_title_transformations_dict: {e}")
            raise (f"build_title_transformations_dict: {e}")
        return results

    def get_missing_shnids(self):
        """
        Connects to the SQLite database specified by db_path, executes the query:
        SELECT shnid
        FROM shnlist
        WHERE shnid NOT IN (SELECT shnid FROM checksum_files)
            AND artist_id = 2
        LIMIT 1000;
        
        Returns a list of shnid values.
        
        Args:
            db_path (str): Path to the SQLite database file.
        
        Returns:
            list: A list of shnid values (typically integers).
        """
        
        
        query = """
            SELECT shnid 
            FROM shnlist 
            WHERE shnid NOT IN (SELECT shnid FROM checksum_files)
            AND artist_id = 2 
            LIMIT 1000;
        """
        self.cursor.execute(query)
        # fetchall returns a list of tuples. We assume shnid is the first column.
        results = self.cursor.fetchall()
        shnids = [row[0] for row in results]
        return shnids


    def get_local_checksum_matches(self,checksums:list):
        """
        Retrieves all records from the 'signatures' table for the given checksums.
        Args:
            checksums (list): A list of checksums to search for.
            format for output is [(shnid,md5key),]
        """

        checksum_matches = set()
        b_unmatched_exists = False
        try:
            for checksum in checksums:
                #if row[1] == {}:
                #    raise ValueError(f'Error in file {row[0]}: no tags returned')
                #checksum = row[2]['fingerprint']
                localshnids = self.get_ffp_shnids_checksum(checksum)
                if localshnids:
                    for item in localshnids:
                        checksum_matches.add(item)
                else:
                    #if we have a file that does not match, go ahead and check to see if there are more matches.
                    b_unmatched_exists = True

        except Exception as e:
            logging.error(f"error in get_local_checksum_matches: {e}")
            raise ValueError(f'Error in file get_local_checksum_matches: {e}')
        return (list(checksum_matches), b_unmatched_exists)

    def vacuum_database(self):
        """
        Connects to the SQLite database at db_path and runs the VACUUM command
        to compact the database.
        
        :param db_path: Path to the SQLite database file.
        """
        try:
            
            self.conn.execute("VACUUM;")
            self.conn.commit()
            print(f"Database '{self.db_path}' vacuumed successfully.")
        except sqlite3.Error as e:
            print(f"An error occurred while vacuuming the database: {e}")



    def dump_sqlite_to_csv(self, folder='db/extract'):
        """
        Dumps all tables from the given SQLite database to CSV files.
        Each CSV file is named after its table (e.g., 'table_name.csv') and
        includes a header row with column names. Optionally, CSV files can be
        saved into a specified folder (absolute or relative path).

        Args:
            db_path (str): Path to the SQLite database file.
            folder (str, optional): Directory where CSV files will be saved.
                                    If provided, the folder will be created if it doesn't exist.
        """
        # If a folder is provided, ensure it exists
        if folder:
            os.makedirs(folder, exist_ok=True)

        # Connect to the SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Retrieve the list of table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        for table in tables:
            table_name = table[0]
            csv_filename = f"{table_name}.csv"
            csv_filepath = os.path.join(folder, csv_filename) if folder else csv_filename

            # Query all rows from the table
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()

            # Get column headers from cursor.description
            headers = [description[0] for description in cursor.description]

            # Write the data to a CSV file
            with open(csv_filepath, "w", newline='', encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(headers)  # Write header row
                writer.writerows(rows)    # Write all table rows

            print(f"Exported table '{table_name}' to '{csv_filepath}'")
        
        # Close the database connection
        conn.close()


class ChecksumFile:
    def __init__(self,etreedb:SQLiteEtreeDB,md5key:int):
        self.id = md5key
        filedetails = etreedb.get_checksum_file(self.id)
        if filedetails:
            self.shnid = filedetails[1]
            self.label = filedetails[2]
            self.filename = filedetails[3]
        else: 
            raise ValueError(f'No Matching Checksum returned for {md5key=}')
        self._checksumlist = None
        self.db = etreedb
    @property 
    def checksumlist(self):
        if self._checksumlist is None:
            self._checksumlist = self.load_checksumlist(self.db)
        return self._checksumlist
    
    def load_checksumlist(self,etreedb:SQLiteEtreeDB):
        return etreedb.get_checksums_only_by_md5key(self.id)      

class EtreeRecording:
    def __init__(self,etreedb:SQLiteEtreeDB,shnid:int,md5key:int=None):
        self.id = shnid
        self.md5key = md5key
        details = etreedb.get_shnid_details(self.id)
        self.date = None
        if details is None:
            self.date = None  # or set a default value / log a warning
            logging.error(f"No event details found for match: {self.id}")
            raise ValueError(f"No event details found for match: {self.id}")
        else:
            self.date = details[0]        
        # if details:
        #     self.date = details[0]
        # else:
        #     self.date = None
            self.etreevenue = details[1]
            self.source = details[2]
            self.artist = etreedb.get_artist_name(details[3])
            self.venue = details[4]
            self.city = details[5]
        self._checksums = None
        self.db = etreedb
        self._tracks = None

    @property
    def checksums(self):
        if self._checksums is None:
            self._checksums = self._load_checksums(self.db)
        return self._checksums  
            
    def _load_checksums(self,etreedb:SQLiteEtreeDB):
        checksumlist = self.db.get_checksum_files(self.id,self.md5key)
        return [ChecksumFile(etreedb,x[0]) for x in checksumlist]

    @property
    def tracks(self):
        if self._tracks is None:
            self._tracks = self._load_tracks(self.db)
        return self._tracks          

    def _load_tracks(self,etreedb:SQLiteEtreeDB):
        tracklist = etreedb.get_track_metadata(self.id,self.md5key)
        #print(tracklist)
        return [Track(*track) for track in tracklist]

    def get_checksum(self, md5key: int):
        """
        Return the ChecksumFile from self.checksums with the given md5key.
        If no match is found, return None.
        """
        for checksum in self.checksums:
            if checksum.id == md5key:
                return checksum
        return None
    def get_track_by_checksum(self, checksum):
        for track in self.tracks:
            if track.fingerprint == checksum:
                return track

    def build_info_file(self):
        #TODO: add gazinta substitution here, use config file for title format
        print (f"Artist: {self.artist}")
        print (f'Album: {self.date} {self.etreevenue} {'['+self.tracks[0].bitabbrev+']' if self.tracks[0].bitabbrev else ''} {'('+str(self.id)+')'}')
            
        print (f'Comment: {self.source}')
        for track in self.tracks:
            print(f"{'d'+track.disc.split('/')[0] if track.disc else ''}{'t'+track.tracknum.split('/')[0] +
                                                                         '. ' if track.tracknum else ''}{track.title_clean}{' ->' if track.gazinta == 'T' else ''} [{track.length}]")

class Track:
    def __init__(self,shnid, disc_number, track_number, title, fingerprint, bit_depth, frequency, length, channels, filename, md5key,title_clean,gazinta):
        self.shnid = shnid
        self.disc = disc_number
        self.tracknum = track_number
        self.title = title_clean
        self.fingerprint = fingerprint
        self.bit_depth = bit_depth
        self.frequency = frequency
        self.length = length
        self.channels = channels
        self.filename = filename
        self.md5key = md5key
        #self.title_clean = title_clean
        self.gazinta = gazinta
        self.bitabbrev = bit_depth+'-'+frequency.rstrip("0")

def copy_file(source_path: str, copy_path: str):
    """
    Copies a file from source_path to copy_path.
    Overwrites the destination file if it exists.
    Raises a ValueError if the source and destination paths are identical.
    
    Args:
        source_path (str): The full path of the file to copy.
        copy_path (str): The full path where the file should be copied.
    """
    source_abs = os.path.abspath(source_path)
    copy_abs = os.path.abspath(copy_path)
    
    if source_abs == copy_abs:
        raise ValueError("Error: Source and destination paths are identical.")
    
    try:
        shutil.copy2(source_abs, copy_abs)
        print(f"Successfully copied from '{source_abs}' to '{copy_abs}'.")
    except Exception as e:
        print(f"Error copying file from '{source_abs}' to '{copy_abs}': {e}")
        raise

def create_zip_archive(zip_name: str, items: list):
    """
    Creates a zip file with the specified name and adds all items in the list.
    Items are expected to be full paths to files. The file will be overwritten
    if it already exists.

    Args:
        zip_name (str): The path and name for the output zip archive.
        items (list): A list of file paths to add to the archive.
    """
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in items:
            if os.path.exists(item):
                # Use os.path.basename(item) as arcname to store only the file name
                zipf.write(item, arcname=os.path.basename(item))
            else:
                print(f"Warning: {item} does not exist and will be skipped.")
    print(f"Successfully created zip archive: {zip_name}")

if __name__ == "__main__":
    db_path="db/etree_scrape.db"
    db_copy_path = "db/etree_tag_db.db"
    zip_path = "db/etree_tag_db.zip"
    db = SQLiteEtreeDB(db_path,log_level=logging.INFO)  # Change log level as needed
    #rec = EtreeRecording(db,124439)
    #rec.build_info_file()  #only works if the track metadata is populated. 
    #db.cursor.execute('SELECT COUNT(*) FROM track_metadata;')
    #count = db.cursor.fetchone()[0]
    #print(f'{count=}')
    #db.parse_venuesource()
    db.dump_sqlite_to_csv()
    db.close()
    copy_file(db_path,db_copy_path)
    create_zip_archive(zip_path,[db_copy_path])
