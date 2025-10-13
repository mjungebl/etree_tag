"""Deprecated helpers extracted from losslessfiles.py.
These functions are kept for reference but are no longer used by the active codebase.
"""

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mutagen.flac import FLAC

def generate_st5_for_folder(
    shntool_exe: str, folder: str, st5_filename: str, audiofiles: list
):
    """
    In 'folder', run:
      shntool.exe hash -m *.flac > st5_filename
    capturing stdout => st5_filename.
    """
    # cmd = [
    #    shntool_exe,
    #    "hash",
    #    "-m",
    #    "*.flac"
    # ]
    st5_path = os.path.join(folder, st5_filename)
    print(f"[ST5 from: {folder} => {st5_filename}]")
    # proc = subprocess.run(cmd, cwd=folder, capture_output=True, text=True)
    # with open(st5_path, "w", encoding="utf-8") as f:
    #    f.write(proc.stdout)
    st5_results = []
    with ThreadPoolExecutor() as executor:
        # futures = {executor.submit(verifyflacfile, filenm,checksum,self.flacpath,self.metaflacpath,self.name,self.location): \
        #        (filenm,checksum) for (filenm,checksum) in list(self.signatures.items())}
        futures = [
            executor.submit(generate_st5_for_file, shntool_exe, file, folder)
            for file in audiofiles
        ]
        for future in as_completed(futures):
            message = future.result()
            st5_results.append(message)

        st5data = "".join([x[2] for x in sorted(st5_results)])
        returncode = 0
        for rc in [x[1] for x in sorted(st5_results)]:
            if rc != 0:
                returncode = rc
    with open(st5_path, "w", encoding="utf-8") as f:
        f.write(st5data)
    return (st5_path, returncode)


def generate_st5_for_file(shntool_exe: str, file: str, folder: str):
    """
    In 'folder', run:
      shntool.exe hash -m *.shn > st5_filename
    capturing stdout => st5_filename.
    """
    # print(f'{folder=}')
    cmd = [shntool_exe, "hash", "-m", file]
    # st5_path = os.path.join(folder, st5_filename)
    # print(f"[ST5 from SHN] {folder} => {st5_filename}")
    proc = subprocess.run(cmd, cwd=folder, capture_output=True, text=True)
    # with open(st5_path, "w", encoding="utf-8") as f:
    #    f.write(proc.stdout)
    return (file, proc.returncode, proc.stdout, proc.stderr, proc)


def rename_child_folders_remove_x_segment(parent_folder):
    """
    For each immediate child folder of parent_folder, this function searches for any
    occurrence of a substring that matches the pattern: period, one or more 'x' or 'X', period.
    When such a substring is found, it is removed (i.e. replaced with a single period).

    For example:
        "artist.xx.2001-05-01.rest" becomes "artist.2001-05-01.rest"
        "band.X.X.track" becomes "band..track" which may then be further normalized
          if desired.

    The function renames the folders accordingly and returns two lists:
        - renamed: a list of tuples (old_folder_name, new_folder_name)
        - unmatched: a list of folder names that did not contain the pattern.

    Parameters:
        parent_folder (str): The path to the parent folder whose immediate child folders
                             will be processed.

    Returns:
        tuple: (renamed, unmatched)
    """
    renamed = []
    unmatched = []

    # Pattern to match a period, one or more x (case-insensitive), then a period.
    pattern = re.compile(r"\.[xX]+\.")

    for entry in os.listdir(parent_folder):
        entry_path = os.path.join(parent_folder, entry)
        if not os.path.isdir(entry_path):
            continue  # Process only directories

        # Check for the pattern.
        if pattern.search(entry):
            # Replace all occurrences of the pattern with a single period.
            new_name = pattern.sub(".", entry)
            # Only rename if the new name is different.
            if new_name != entry:
                new_path = os.path.join(parent_folder, new_name)
                try:
                    os.rename(entry_path, new_path)
                    renamed.append((entry, new_name))
                    print(f"Renamed: {entry} -> {new_name}")
                except Exception as e:
                    print(f"Error renaming {entry} to {new_name}: {e}")
            else:
                unmatched.append(entry)
        else:
            unmatched.append(entry)

    return renamed


def rename_child_folders_strip_leading_zeros(parent_folder):
    """
    Splits the given string on periods, and for any segment that consists solely
    of digits, converts it to an integer (thus removing leading zeros) and then back to a string.
    Finally, the segments are re-joined with periods.

    For example:
      "gd1991-03-31.99386.099386.Greensboro,NC.mtx.south.flac16"
    becomes:
      "gd1991-03-31.99386.99386.Greensboro,NC.mtx.south.flac16"
    """
    renamed = []
    for entry in os.listdir(parent_folder):
        entry_path = os.path.join(parent_folder, entry)
        if not os.path.isdir(entry_path):
            continue  # Skip if not a folder
        segments = entry.split(".")
        print(segments)
        new_segments = []
        for seg in segments:
            if seg.isdigit():
                # Converting to int removes leading zeros, then back to string.
                newseg = str(seg).lstrip("0")
                if newseg not in new_segments:
                    new_segments.append(newseg)
            else:
                if seg not in new_segments:
                    new_segments.append(seg)
        new_name = ".".join(new_segments)
        if new_name != entry:
            new_path = os.path.join(parent_folder, new_name)
            try:
                os.rename(entry_path, new_path)
                renamed.append((entry, new_name))
                print(f"Renamed: {entry} -> {new_name}")
            except Exception as e:
                print(f"Error renaming {entry} to {new_name}: {e}")

    return renamed


def two_char_year_folder_fix(parent_folder):
    """
    Renames all direct child folders in parent_folder that start with an artist abbreviation
    followed by a date in the format 'yy-mm-dd' to a format with a four-digit year.

    For a folder matching:
      [ArtistAbbr][yy]-[mm]-[dd][rest]
    it will be renamed to:
      [ArtistAbbr][yyyy]-[mm]-[dd][rest]

    The two-digit year is converted using this heuristic:
      if int(yy) < 50, then yyyy = "20" + yy; else yyyy = "19" + yy.

    Folders that already match the four-digit pattern (e.g. ArtistAbbryyyy-mm-dd...) are skipped.
    Any folders that do not match either pattern are collected in a list.

    Parameters:
        parent_folder (str): The folder in which to process child directories.

    Returns:
        tuple: Two lists:
            - renamed: list of tuples (old_name, new_name) for each renamed folder.
            - unmatched: list of folder names that did not match either pattern.
    """
    # Pattern for two-digit year e.g. "gd87-01-28.rest..."
    pattern_2digit = re.compile(
        r"^(?P<abbr>[A-Za-z]+)(?P<yy>\d{2})-(?P<mm>\d{2})-(?P<dd>\d{2})(?P<rest>.*)$"
    )
    # Pattern for four-digit year e.g. "gd1987-01-28.rest..."
    pattern_4digit = re.compile(
        r"^(?P<abbr>[A-Za-z]+)(?P<yyyy>\d{4})-(?P<mm>\d{2})-(?P<dd>\d{2})(?P<rest>.*)$"
    )

    renamed = []
    unmatched = []

    # Process only direct children (non-recursive)
    for entry in os.listdir(parent_folder):
        entry_path = os.path.join(parent_folder, entry)
        if not os.path.isdir(entry_path):
            continue  # skip non-directories

        # Check for four-digit year pattern first.
        if pattern_4digit.match(entry):
            # Already in correct format; skip renaming.
            continue

        m = pattern_2digit.match(entry)
        if m:
            abbr = m.group("abbr")
            yy = m.group("yy")
            mm = m.group("mm")
            dd = m.group("dd")
            rest = m.group("rest")

            # Use a heuristic to convert two-digit year to four digits.
            # Here, if int(yy) < 50 we assume 2000+; otherwise, 1900+.
            year_int = int(yy)
            if year_int < 50:
                yyyy = "20" + yy
            else:
                yyyy = "19" + yy

            new_name = f"{abbr}{yyyy}-{mm}-{dd}{rest}"
            new_path = os.path.join(parent_folder, new_name)

            try:
                print(f"Renaming: {entry} -> {new_name}")
                os.rename(entry_path, new_path)
                renamed.append((entry, new_name))
            except Exception as e:
                print(f"Error renaming {entry} to {new_name}: {e}")
        else:
            unmatched.append(entry)

    return renamed, unmatched


def foldercleanup(parentdirectory):
    """
    call all of the cleanup functions on new folders.
    """
    parentdirectory = Path(parentdirectory).as_posix()

    # print(f'{ren=}, {unmatch=}')
    ren = rename_child_folders_strip_leading_zeros(parentdirectory)
    for orig, new in ren:
        print(f"Renamed: {orig} to {new}")

    ren, unmatch = two_char_year_folder_fix(parentdirectory)
    for folder in ren:
        print(f"Renamed: {folder}")

    for folder in unmatch:
        print(f"Unable to rename: {folder}")

    rename_child_folders_remove_x_segment(parentdirectory)
