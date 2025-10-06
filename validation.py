from __future__ import annotations
from pathlib import Path
import logging
from typing import Iterable, Tuple
from collections.abc import Mapping, Sequence

from recordingfiles import RecordingFolder
from services.config import load_app_config
from sqliteetreedb import SQLiteEtreeDB, EtreeRecording


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def check_and_rename(
    folder: str,
    db: SQLiteEtreeDB,
    standardize_artist_abbrev: Mapping[str, Sequence[str]] | None = None,
) -> Tuple[str, bool, list[str]]:
    """Check a folder against the database and rename if a match is found.

    Returns a tuple ``(new_folder, matched, errors)``.
    """
    rec_folder = RecordingFolder(
        folder,
        db,
        standardize_artist_abbrev=standardize_artist_abbrev,
    )
    match: EtreeRecording | None = rec_folder._find_matching_recording()
    if match:
        original = rec_folder.folder
        rec_folder._standardize_folder_year(match)
        try:
            db.insert_folder_shnid_log(match.id, rec_folder.folder.name)
        except Exception as e:
            logging.error(f"Failed to log folder {rec_folder.folder}: {e}")
        if rec_folder.folder != original:
            logging.info(f"Renamed {original} -> {rec_folder.folder}")
        _, errors = rec_folder.verify_fingerprint()
        return str(rec_folder.folder), True, errors
    return folder, False, []


def validate_folders(
    folders: Iterable[str],
    db_path: str = "db/etree_scrape.db",
    standardize_artist_abbrev: Mapping[str, Sequence[str]] | None = None,
) -> list[Tuple[str, bool, list[str]]]:
    """Validate each folder and rename it when a match is found.

    Args:
        folders: Iterable of folder paths to inspect.
        db_path: Path to the SQLite database used for matching.
        standardize_artist_abbrev: Optional alias mapping applied during normalization.

    Returns:
        List of ``(folder, matched, errors)`` tuples for every processed folder.
    """
    db = SQLiteEtreeDB(db_path)
    results = []
    for fld in folders:
        try:
            results.append(
                check_and_rename(
                    fld,
                    db,
                    standardize_artist_abbrev=standardize_artist_abbrev,
                )
            )
        except Exception as e:
            logging.error(f"Error processing {fld}: {e}")
            results.append((fld, False, [str(e)]))
    db.close()
    return results


def validate_parent_folder(
    parent: str,
    db_path: str = "db/etree_scrape.db",
    standardize_artist_abbrev: Mapping[str, Sequence[str]] | None = None,
) -> list[Tuple[str, bool, list[str]]]:
    """Validate every subfolder of ``parent`` using :func:`validate_folders`.

    Args:
        parent: Directory containing show folders to inspect.
        db_path: Path to the SQLite database used for matching.
        standardize_artist_abbrev: Optional alias mapping applied during normalization.

    Returns:
        List of ``(folder, matched, errors)`` tuples, one per child folder.
    """
    parent_path = Path(parent)
    folders = sorted(str(f) for f in parent_path.iterdir() if f.is_dir())
    return validate_folders(
        folders,
        db_path,
        standardize_artist_abbrev=standardize_artist_abbrev,
    )


if __name__ == "__main__":
    import argparse

    # parent_folder = r"X:\Downloads\_FTP\_mismatches_RETRY_RESEARCH"
    parent_folder = r"X:\Downloads\_FTP\_Tag_test"
    parser = argparse.ArgumentParser(
        description="Validate recording folders against the database"
    )
    parser.add_argument("folders", nargs="*", help="Folder paths to validate")
    if parent_folder:
        parser.add_argument(
            "--parent",
            default=parent_folder,
            help="Parent directory containing show folders",
        )
    else:
        parser.add_argument("--parent", help="Parent directory containing show folders")
    parser.add_argument(
        "--db", default="db/etree_scrape.db", help="Path to SQLite database"
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().with_name("config.toml")),
        help="Path to application configuration file",
    )

    args = parser.parse_args()

    try:
        app_config = load_app_config(args.config)
        alias_overrides = app_config.recording_folder.standardize_artist_abbrev or {}
    except Exception as exc:  # pragma: no cover - configuration failure is user-driven
        logging.error("Failed to load configuration from %s: %s", args.config, exc)
        alias_overrides = {}

    if args.parent:
        outcomes = validate_parent_folder(
            args.parent,
            args.db,
            standardize_artist_abbrev=alias_overrides,
        )
    else:
        outcomes = validate_folders(
            args.folders,
            args.db,
            standardize_artist_abbrev=alias_overrides,
        )
    mismatches = []
    errors: list[str] = []
    for folder, matched, ferr in outcomes:
        status = "matched" if matched else "no match"
        if status == "matched":
            print(f"{folder}: {status}")
            errors.extend(ferr)
        else:
            mismatches.append(folder)
    if mismatches:
        print(f"The following {len(mismatches)} items did not match an existing shnid:")
        for folder in mismatches:
            print(folder)
    if errors:
        print("Fingerprint verification errors:")
        for err in errors:
            print(err)
            logging.error(err)
    else:
        print("All matched files verified successfully.")

#python validation.py --parent "X:\Downloads\_FTP\_Tag_test" --config config.toml


