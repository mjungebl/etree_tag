from __future__ import annotations
from pathlib import Path
import logging
from typing import Iterable, Tuple

from recordingfiles import RecordingFolder
from sqliteetreedb import SQLiteEtreeDB, EtreeRecording


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def check_and_rename(folder: str, db: SQLiteEtreeDB) -> Tuple[str, bool, list[str]]:
    """Check a folder against the database and rename if a match is found.

    Parameters
    ----------
    folder: str
        Path to the concert folder.
    db: SQLiteEtreeDB
        Database instance used for matching.

    Returns
    -------
    tuple
        A tuple ``(new_folder, matched, errors)`` where ``new_folder`` is the
        final folder path, ``matched`` indicates whether a database match was
        found, and ``errors`` contains any fingerprint verification errors.
    """
    rec_folder = RecordingFolder(folder, db)
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
    folders: Iterable[str], db_path: str = "db/etree_scrape.db"
) -> list[Tuple[str, bool, list[str]]]:
    """Validate and rename a sequence of folders.

    Parameters
    ----------
    folders: iterable of str
        Folder paths to process.
    db_path: str
        Path to the SQLite database.

    Returns
    -------
    list of tuple
        A list of ``(folder, matched, errors)`` tuples for each processed folder.
    """
    db = SQLiteEtreeDB(db_path)
    results = []
    for fld in folders:
        try:
            results.append(check_and_rename(fld, db))
        except Exception as e:
            logging.error(f"Error processing {fld}: {e}")
            results.append((fld, False, [str(e)]))
    db.close()
    return results


def validate_parent_folder(
    parent: str, db_path: str = "db/etree_scrape.db"
) -> list[Tuple[str, bool, list[str]]]:
    """Validate all subfolders of a parent directory.

    Parameters
    ----------
    parent: str
        Path to a directory containing show folders.
    db_path: str
        Path to the SQLite database.

    Returns
    -------
    list of tuple
        Results from :func:`validate_folders` for each subfolder.
    """
    parent_path = Path(parent)
    folders = sorted(str(f) for f in parent_path.iterdir() if f.is_dir())
    return validate_folders(folders, db_path)


if __name__ == "__main__":
    import argparse

    # parent_folder = r"X:\Downloads\_FTP\_mismatches_RETRY_RESEARCH"
    parent_folder = r"X:\Downloads\_FTP\_Concerts_Unofficial\Phish"
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
    args = parser.parse_args()

    if args.parent:
        outcomes = validate_parent_folder(args.parent, args.db)
    else:
        outcomes = validate_folders(args.folders, args.db)
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
