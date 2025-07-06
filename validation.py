from __future__ import annotations
from pathlib import Path
import logging
from typing import Iterable, Tuple

from recordingfiles import RecordingFolder
from sqliteetreedb import SQLiteEtreeDB, EtreeRecording


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def check_and_rename(folder: str, db: SQLiteEtreeDB) -> Tuple[str, bool]:
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
        A tuple ``(new_folder, matched)`` where ``new_folder`` is the final folder
        path and ``matched`` indicates whether a database match was found.
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
        return str(rec_folder.folder), True
    return folder, False


def validate_folders(folders: Iterable[str], db_path: str = "db/etree_scrape.db") -> list[Tuple[str, bool]]:
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
        A list of ``(folder, matched)`` tuples for each processed folder.
    """
    db = SQLiteEtreeDB(db_path)
    results = []
    for fld in folders:
        try:
            results.append(check_and_rename(fld, db))
        except Exception as e:
            logging.error(f"Error processing {fld}: {e}")
            results.append((fld, False))
    db.close()
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate recording folders against the database")
    parser.add_argument("folders", nargs="+", help="Folder paths to validate")
    parser.add_argument("--db", default="db/etree_scrape.db", help="Path to SQLite database")
    args = parser.parse_args()

    outcomes = validate_folders(args.folders, args.db)
    for folder, matched in outcomes:
        status = "matched" if matched else "no match"
        print(f"{folder}: {status}")
