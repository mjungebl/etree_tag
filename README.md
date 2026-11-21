# Concert Tagger

Concert Tagger is a command-line utility for matching local FLAC concert folders with the bundled Etree database, tagging the audio files, and managing cover artwork. The current tooling is built around Grateful Dead collections, but any artist present in the database can be processed.

---

## Highlights
- Match folders to Etree shnids by verifying FLAC checksums.
- Import disc/track numbers, titles, and show metadata directly from the database. If track information is not present in the database, an attempt to parse the info file will be made. There is an optional filename-based fallback, but this is left off by default as the filenames are not always titles.
- Embed and manage artwork (including `folder.jpg`) according to per-artist rules.
- Structured logging with explicit error codes so batch runs are easy to monitor.

---

## Requirements
- **Python 3.11+** (tested on 3.13).
- Python dependencies (installed automatically if you use the shipped `.venv`/`uv` workflow):
  - `mutagen`
  - `tqdm`
  - `tomllib` (shipped with Python =3.11)
- SQLite Etree database (`db/etree_scrape.db`). The first run seeds it from the CSV snapshots under `db/csv/`.

### Quick Setup
```bash
# Option 1: let uv manage the environment (creates .venv automatically)
uv sync

# Option 2: create/activate your own venv and install dependencies manually
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install mutagen tqdm
```

---

## CLI Usage
Run the orchestrator via `cli.py`:

```bash
python cli.py --help
```

Typical flows:

```bash
# Process every show folder directly under the parent directory
python cli.py --parent-folder "X:/Downloads/_FTP/_Tag_test"

# Tag explicit folders and remove existing tags first
python cli.py \
  "X:/Shows/gd1985-11-17.172965" "X:/Shows/gd1974-06-18.002341" \
  --clear-tags

# Use alternate config/db locations and a custom log file
python cli.py --config config.toml --database db/etree_scrape.db \
  --log-file logs/tagger.log --parent-folder "X:/Shows_to_process"
```

CLI options of note:
- `--parent-folder`: expand immediate subdirectories and process each as a show.
- `--clear-tags`: drop all non-artwork FLAC tags before writing new metadata.
- `--log-file`: where structured logs land (console output mirrors INFO by default).
- `--config`, `--database`: override the default config or SQLite locations.

Exit codes are non-zero on failures so the command works well in batch scripts.

### Logging
Setup defaults the base log path to `tagger_logs/tag_log.log` under your saved
library or show folder. Each run prefixes the filename with a timestamp, for
example `2026-11-21_14-30-05_123456_tag_log.log`. Choose a different base path
during setup, edit `run.log_file` in your
user TOML, or use `--log-file` for a single run. Setup offers verbose
diagnostic logging, which defaults to off. Set `preferences.verbose_logging = true`
in your user TOML for DEBUG-level detail in the terminal and log file.

---

## First-run setup

Run `python cli.py` in an interactive terminal. Setup shows the defaults as it
asks for your library, catalog, logging, and artwork preferences. Press Enter to
accept a displayed default. Setup saves your preferences and prints the full
path. You can edit that TOML file in a text editor. Setup leaves show files
untouched.

The saved file is `%APPDATA%\EtreeTag\config.toml` on Windows and
`$XDG_CONFIG_HOME/etree-tag/config.toml` on other platforms, with
`~/.config/etree-tag/config.toml` used when XDG_CONFIG_HOME is unset.
Later runs use your saved library and preferences. Passing show folders or
`--parent-folder` overrides the saved library for that run. Use `--clear-tags`
or `--no-clear-tags` to override the saved tag-clearing preference.

The shipped `config.toml` supplies defaults. To keep using an existing TOML
directly, pass `--config PATH`. To adopt existing choices into the managed
configuration, transfer them to the file created by setup, keeping its
`config_version` and making any paths relative to that file or absolute.

## Configuration
`config.toml` drives behaviour. Key settings:

```toml
[preferences]
year_format = "YYYY"
segue_string = "->"
soundboard_abbrev = "SBD"
aud_abbrev = "AUD"
verbose_logging = false
enable_filename_fallback = false  # opt-in for filename-derived metadata

[album_tag]
include_bitrate = true
include_bitrate_not16_only = true
include_shnid = true
include_venue = false
include_city = true
order = ["show_date", "city", "venue", "recording_type", "shnid", "bitrate"]

[cover]
clear_existing_artwork = false
retain_existing_artwork = true

[cover.default_images]
gd = "GD_Art/default.jpg"

[cover.artwork_folders]
gd = ["GD_Art/EE_Artwork/", "GD_Art/TV_Artwork/"]
```

### Filename Fallback
The importer defaults to info-file metadata. To let the legacy filename parser fill in disc/track numbers and titles when info files are missing, set:

```toml
[preferences]
enable_filename_fallback = true
```

When the flag is `false`, metadata import stops with a `MetadataImportError` so callers can handle the failure explicitly.

---

## Database Notes
- On first launch, the tool builds `db/etree_scrape.db` from `db/csv/`.
- `sqliteetreedb.py` contains the read/write facade used by the tagging workflow.
- Artist abbreviations (e.g., `gd`) drive artwork lookup; missing abbreviations simply skip artwork tagging with a log message.

---

## Development & Testing
```bash
python -m pytest
```

The project relies on structured logging internally. Enable verbose mode if you need to track down per-file debug output.

---

## License
Released under the MIT License. See `LICENSE` for details.



