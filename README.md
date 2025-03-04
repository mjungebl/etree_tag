# Concert Tagger

**Concert Tagger** is a Python script that tags FLAC music files (especially Grateful Dead recordings) with metadata and artwork. It:

- Reads checksums from flac files in local folders to match a recording against an SQLite-based Etree database (accessed via `sqliteetreedb.py`).
- Adds or updates tags (artist, album, track info, etc.) in the FLAC files.
- Finds and embeds cover artwork if available.
- Optionally clears existing embedded artwork before adding the new image. (currently requires a code change)
- Copies an artwork file (`folder.jpg`) into each folder for quick visual identification.

---

## Table of Contents

1. [Requirements](#requirements)  
2. [Usage](#usage)  
4. [Script Overview](#script-overview)
5. [Configuration](#configuration)  
6. [License](#license)

---

## Requirements

1. **Python 3.11+** (recommended, though older versions may work).
2. **Packages**:
   - [mutagen](https://mutagen.readthedocs.io/) (for reading/writing FLAC tags)
   - [tqdm](https://pypi.org/project/tqdm/) (for progress bars)
   - `tomllib`  
     - Bundled with Python 3.11+  
     - For Python < 3.11, install [tomli](https://pypi.org/project/tomli/) and adjust imports.
3. **SQLite Database** for Etree recordings (`sqliteetreedb.py` should handle it).
4. **`recordingfiles.py`** module to locate FLAC files and checksums.


## Usage
Best way to get started is to use uv sync to get this up and running. Otherwise set up an environment with the requirements listed above. (only mutagen and tqdn need to be installed if using python 3.11 or greater. I used 3.13)
My current recommendation is to run this from the tagger.py script. In the section at the bottom, change the "parentfolderpath" to the path to a folder that contains show folders.
I'd create a new folder and copy one or two shows into that folder and see how it works rather than running it on a lot of files at once. 

parentfolderpath = r'c:/showstotag' #note that I used a forward slash, this is not necessary on Windows, but make sure the string is precedded with the r.
Put a couple of shows in that folder and try running it. Currently it won't tag song titles unless they're in the database already (over 8,000 are in there though). It will only do the album, artwork and comments. 

There is a script called "InfoFileTagger.py" that can be used to tag the songs. It requires a text file in the directory to contain the shnid and have numbered tracks d1t01 if disc numbers are preferred or 01. song name, 01 song name, or a couple of other formats. I'll be incorporating that functionality directly in a later version. 

NOTE: the call create the SQLiteEtreeDB passes a database in (sqlite). initially that database won't exist. when it initializes it will be populated from the csvs contained in the folder "db/csv/". If you move those files and have not initialized the database, you'll need to change the relative path to the csv files in sqliteetreedb.py. I'll be adding that to the config at some point, but for now, I'd leave them alone. That was a last minute change because the db is too large for github.  Also, as I ahve not added my scraping code to this project, this give a manual way to add more info to the db, for anyone inclined to do this that is not comfortable working with databases. 
The call I'm referring to is this one:
etreedb = SQLiteEtreeDB(db_path="db/etree_tag_dbv2.db")

My recommendation for now is to leave things as-is and jsut run it.  I'll be making updates in the coming weeks as I have time.

---

## Configuration (CURRENTLY ONLY THE COVER SECTION IS ENABLED)

A sample `config.toml` file might look like this (which is also included):

```toml
[cover]
artwork_folders = [
  "X:/Artwork/Dead",
  "Y:/Shared/AlbumArt/GD"
]
defaultimage_path = "X:/Artwork/default.jpg"

[preferences]
year_format = "%Y"
segue_string = "->"
soundboard_abbrev = "SBD"
aud_abbrev = "AUD"
matrix_abbrev = "MTRX"
ultramatrix_abbrev = "UMTX"

[album_tag]
include_bitrate = true
include_bitrate_not16_only = true
include_venue = true
include_city = true
order = "date_venue"
prefix = ""
suffix = ""
