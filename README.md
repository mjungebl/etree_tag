# Concert Tagger

**Concert Tagger** is a Python script that tags FLAC music files (especially Grateful Dead recordings) with metadata and artwork. It:

- Reads checksums from local folders to match a recording against an SQLite-based Etree database (`sqliteetreedb.py`).
- Adds or updates tags (artist, album, track info, etc.) in the FLAC files.
- Finds and embeds cover artwork if available.
- Optionally clears existing embedded artwork before adding the new image.
- Copies an artwork file (`folder.jpg`) into each folder for quick visual identification.

---

## Table of Contents

1. [Requirements](#requirements)  
2. [Configuration](#configuration)  
3. [Usage](#usage)  
4. [Script Overview](#script-overview)  
5. [License](#license)

---

## Requirements

1. **Python 3.9+** (recommended, though older versions may work).
2. **Packages**:
   - [mutagen](https://mutagen.readthedocs.io/) (for reading/writing FLAC tags)
   - [tqdm](https://pypi.org/project/tqdm/) (for progress bars)
   - `tomllib`  
     - Bundled with Python 3.11+  
     - For Python < 3.11, install [tomli](https://pypi.org/project/tomli/) and adjust imports.
3. **SQLite Database** for Etree recordings (`sqliteetreedb.py` should handle it).
4. **`recordingfiles.py`** module to locate FLAC files and checksums.

---

## Configuration (CURRENTLY ONLY THE COVER SECTION IS ENABLED)

A sample `config.toml` file might look like this:

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

x