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
3. [Configuration](#configuration)  
4. [License](#license)

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
Best way to get started is to run "uv sync" in the folder after downloading to get this up and running. This will create the venv with the requirements specified.
Alternatively, you can manually set up a Python environment by installing the required packages listed above. (While this is subject to change, currently only mutagen and tqdm need to be installed if using Python 3.11 or greater; I used Python 3.13)
My current recommendation is to execute the script from the `tagger.py` file. In the section at the bottom, there are 3 sections that I outlined depending on the use case. Uncomment the one that matches your usage.
1. if using a single folder, or specific folders use a python list of path(s): 
    concert_folders = [r"Z:\Music\Grateful Dead\gd1987\gd1987-01-28.140689.UltraMatrixSBD.cm.miller.flac24"]
2. "single parent folder" - Edit the "parentfolder" to reflect a path to a folder containing show folders immediately beneath it, such as a "year" of shows
```python
    parentfolder = r'Z:\Music\Grateful Dead\gd1994'
```
    concert_folders = sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()])
3. "two level deep folder enumeration for processing" -- Edit the "parentofparents" to reflect a path to a folder containing folders that contain show folders, such as the path to a folder that contains multiple year folders of shows
```python
    parentofparents =r'M:/To_Tag'
    parentlist = sorted([f.path.replace('\\','/') for f in os.scandir(parentofparents) if f.is_dir()])
    for parentfolder in parentlist:
        if parentfolder.lower().endswith("fail"): #addl filtering, exclude if the folder name ends with fail
            continue
        concert_folders.extend(sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()]))
```
NOTE: I'd create a new folder and copy one or two shows into that folder and see how it works rather than running it on a lot of files at once. Put a couple of shows in that folder and try running it. Currently it won't tag song titles unless they're in the database already (over 8,000 are in there though). It will only do the album, artwork and comments. 

There is a script called "InfoFileTagger.py" that can be used to tag the songs. It requires a text file in the directory to contain the shnid and have numbered tracks d1t01 if disc numbers are preferred or 01. song name, 01 song name, or a couple of other formats. I'll be incorporating that functionality directly in a later version. 

NOTE: the call create the SQLiteEtreeDB passes a database in (sqlite). initially that database won't exist. when it initializes it will be populated from the csvs contained in the folder "db/csv/". If you move those files and have not initialized the database, you'll need to change the relative path to the csv files in sqliteetreedb.py. I'll be adding that to the config at some point, but for now, I'd leave them alone. That was a last minute change because the db is too large for github.  Also, as I have not added my scraping code to this project, this allows "manual" way to add more info to the db, for anyone inclined to do this that is not comfortable working with databases.
The artists table now includes an `ArtistAbbrev` column. These abbreviations are
used when locating artwork files (e.g. `gd` for Grateful Dead). Configuration
for artwork directories is keyed by these abbreviations. If an artist
abbreviation is not listed, artwork tagging is skipped and a notice is logged.
The call I'm referring to is this one:
etreedb = SQLiteEtreeDB(db_path="db/etree_tag_dbv2.db")



---

## Configuration
See config.toml file for additional explanation.


```toml
[preferences]
# Set the year format for tags.
# Valid options: "YYYY" or "YY"
year_format = "YYYY"
segue_string = "->"
soundboard_abbrev = "SBD"
aud_abbrev = "AUD"
matrix_abbrev = "MTX"
ultramatrix_abbrev = "Ultramatrix"
verbose_logging = false
[album_tag]
include_bitrate = true
include_bitrate_not16_only = true
include_shnid    = true
include_venue   = false
include_city    = true
order = ["show_date","city","venue", "recording_type", "shnid","bitrate"]
prefix = ['',' ',' ',' ',' (',' [']
suffix = ['','','','',')',']']

[cover]
clear_existing_artwork = false # Clears existing artwork tags and sets a new one
retain_existing_artwork = true
defaultimage_path = 'GD_Art/default.jpg'

[cover.artwork_folders]
gd = ['GD_Art/EE_Artwork/', 'GD_Art/TV_Artwork/']
```
## License

This project is licensed under the MIT License. You are free to use, modify, and distribute this software. See the (LICENSE) file for more details.
