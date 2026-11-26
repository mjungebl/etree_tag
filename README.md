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
- `--log-file`: where structured run diagnostics and per-show tracebacks are saved.
- `--config`, `--database`: override the default config or SQLite locations.

Exit codes are non-zero on failures so the command works well in batch scripts.

When there are changes to approve, the CLI prints a preview and writes a timestamped
`*_changes.txt` manifest alongside the run log. The preview counts shows that
will change, are already tagged per preferences, or are expected to fail.
It lists each blocked show with its reason. Review the manifest
for failure reasons, FLAC tag edits, artwork changes and backups, folder
renames, and catalog imports.
Type exactly `yes` to apply the plan. Enter, any other answer, or end of input
cancels the plan. The CLI skips unchanged FLACs and shows whose files change
after the preview.

### File verification

Run `python cli.py --verify` or set `verify = true` under `[run]` in
your TOML to verify shows before tagging. Use `--no-verify` to override
that setting for one run.

FLAC audio tests require the [Xiph FLAC command-line tool](https://xiph.org/flac/download.html).
Etree Tag tests `supportfiles.flac` (or the `--flac` override), then checks
`PATH` for `flac` on macOS and Linux or `flac.exe` on Windows. If the
tool is missing, the interactive menu can open Xiph's download page, test
an executable path or folder, or exit so you can install the tool and try
again. A working path entered in the menu is saved in managed settings
for future runs. With `--config`, set `supportfiles.flac` in that TOML or
add the executable's folder to `PATH` to reuse it.

SHN files are checked against available `.md5` manifests using Python.
Verification failures block changes to the affected show. Files without a
reference checksum are reported as unverified.

Setup and the version 5 upgrade ask whether to reuse verification receipts
when file verification is enabled. To enable it manually, set
`reuse_verification = true` alongside `verify = true` under `[run]`.
The CLI saves a dated `.etree-verified.json` receipt in each fully verified
show folder. On later runs, it reports the previous verification time and
skips the checksum pass if the tracked audio and applicable MD5 manifests
still match the receipt's file metadata. Changes, including FLAC tag edits,
trigger a fresh check. Use `--reuse-verification` for a one-run opt-in, or
`--verify --no-reuse-verification` to force fresh checks.
New SHN conversions always verify their inputs and outputs.

### Convert SHN-only sets

Version 4 of the user configuration adds these settings during setup or
upgrade.

```toml
[shn_conversion]
enabled = false
compression_level = 8
paranoid = false
```

Enable conversion to losslessly re-encode SHN-only shows before the tagging
preview. Use `--convert-shn` or `--no-convert-shn` to override the saved
choice for one run. Compression accepts FFmpeg levels 0 through 12 and
defaults to 8. Conversion uses FFmpeg from `PATH`, `supportfiles.ffmpeg`,
or `--ffmpeg PATH`, and requires the FLAC command-line tool. It checks available
SHN checksums and tests the new FLACs before publishing them, even when
routine verification is disabled. Standard conversion removes the source SHNs
after successful verification, renames original `.md5` manifests to
`.md5.shn-source` without changing their contents, and keeps companion files.
Conversion writes `SHN-to-FLAC-<shnid>.txt` alongside the tracks
(`SHN-to-FLAC-unknown-SHNID.txt` when the folder name has no SHNID).
Review the SHN conversion manifest and type `yes` before conversion starts.
After conversion, review the separate tagging manifest to approve any tagging
changes.

Enable paranoid mode to preserve the complete original fileset in
`_shn_source`, including SHNs, MD5 manifests, and companion files such as
the info TXT. Paranoid mode also keeps the source SHNs in the show folder.
It checks each copy
byte for byte using SHA-256 and compares the decoded SHN and FLAC audio
before publishing the archive and converted tracks. The current run's log
and conversion manifest are excluded. An existing `_shn_source` directory blocks paranoid conversion
for that show.

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

The **Album tag** section lets you choose the fields in the FLAC album name
and previews the result. Advanced options cover field order, separators, and
recording-type labels such as SBD, AUD, MTX, and Ultramatrix. **Track titles**
offers a segue marker and filename fallback. **Performance date tags** can
write the catalog date to `DATE` and optionally to separate `YEAR`, `MONTH`,
and `DAY` fields.

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

If your saved TOML uses an older schema, run `python cli.py` in an interactive
terminal. Upgrading from version 2 to 3 asks whether to verify files before
tagging. Upgrading from version 1 also asks the Album tag, Track titles, and
Performance date questions. Setup keeps your other preferences, prints the
backup path, and exits before tagging. The backup retains the original
formatting and comments.

## Configuration
`config.toml` drives behaviour. Key settings:

```toml
[preferences]
year_format = "YYYY"
segue_string = ">"
soundboard_abbrev = "SBD"
aud_abbrev = "AUD"
verbose_logging = false
enable_filename_fallback = false  # opt-in for filename-derived metadata
write_date = false                # write the performance date to DATE
write_date_parts = false          # also write YEAR, MONTH, and DAY where known

[album_tag]
include_bitrate = true
include_bitrate_not16_only = true
include_shnid = true
include_venue = false
include_city = true
include_recording_type = true
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



