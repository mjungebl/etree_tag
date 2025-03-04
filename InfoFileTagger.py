#!/usr/bin/env python3
import os
import re
import argparse
import logging
from glob import glob
from mutagen.flac import FLAC

def file_sort_key(filepath):
    base = os.path.splitext(os.path.basename(filepath))[0]
    m = re.search(r"[ds](\d+)[tT](\d+)$", base, re.IGNORECASE)
    if m:
        disc = int(m.group(1))
        track = int(m.group(2))
        return (disc, track)
    else:
        return (float('inf'), base.lower())


def clean_track_name(title):
    """
    Cleans a track title by:
      - Removing time patterns (e.g. "08:05.425")
      - Removing text within square brackets and curly braces
      - Removing all asterisk (*) characters
      - Removing a leading "->" or ">" along with any following whitespace
      - Trimming any leading or trailing whitespace

    If the cleaned title is empty, the original title is returned.
    """
    original = title
    strip_after_n_spaces(title,5)
    #get rid of oddball whitespace
    re.sub(r'[\t\n\r\f\v]+', ' ', title)
    #trim all spaces down to 1
    re.sub(r' {2,}', ' ', title)
    # Remove anything within square brackets.
    title = re.sub(r'\[.*?\]', '', title)
    # Remove anything within curly braces.
    title = re.sub(r'\{.*?\}', '', title)    
    # Remove time patterns with parenthesis (e.g. "06:03" or "06:03.667").
    title = re.sub(r'\(\s*\d{1,2}:\d{2}(?:\.\d{1,3})?\s*\)', '', title)
    # Remove time patterns (e.g. "06:03" or "06:03.667").
    title = re.sub(r'\b\d{1,2}:\d{2}(?:\.\d{1,3})?\b', '', title)

    # Remove all asterisk characters.
    title = title.replace('*', '')
    # Remove a leading "->" or ">" with optional whitespace.
    title = re.sub(r'^\s*(->|>)\s*', '', title)
    #Encore
    if not 'encore break' in title.lower():
        title = re.sub(r"^encore:?\s*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"[\(\[]\s*encore\s*[\)\]]", "", title, flags=re.IGNORECASE)
    #get rid of leading dashes:
    title = re.sub(r'^\s*-\s*', '', title)
    # Strip leading/trailing whitespace.
    cleaned = title.strip()
    return cleaned if cleaned else original

import re

def strip_after_n_spaces(s, n):
    """
    Returns the substring of s up to (but not including) the first occurrence of
    n or more consecutive whitespace characters, provided that doing so leaves a nonempty string.
    Otherwise, returns the original string.
    
    :param s: Input string.
    :param n: Minimum number of consecutive whitespace characters that triggers the cutoff.
    :return: The substring before the whitespace block, or the original string if that would be empty.
    """
    pattern = rf'\s{{{n},}}'
    m = re.search(pattern, s)
    if m:
        idx = m.start()
        if idx > 0:
            result = s[:idx].rstrip()
            if result:
                return result
    return s

# Example usage:
print(strip_after_n_spaces("Keep this part     remove this", 5))  # -> "Keep this part"
print(strip_after_n_spaces("No extra spaces here", 5))            # -> "No extra spaces here"

def tag_flac_files(track_mapping):
    """
    Given a track_mapping dictionary where each key is a FLAC file path and
    each value is a tuple (disc, track, title), tag the FLAC files using Mutagen.
    
    If both the tracknumber and discnumber tags already exist, check that they match
    the generated values. If they don't match, log an error and skip tagging that file.
    """
    for flac_path, (disc, track, title) in track_mapping.items():
        logging.info(f"Tagging file: {flac_path} -> Generated: Disc {disc}, Track {track}: {title}")
        try:
            audio = FLAC(flac_path)
        except Exception as e:
            logging.error(f"Error loading {flac_path}: {e}")
            continue

        existing_track = audio.get("tracknumber")
        existing_disc = audio.get("discnumber")

        if existing_track and existing_disc:
            if existing_track[0] != track or existing_disc[0] != str(disc):
                logging.error(
                    f"Mismatch in {flac_path}: existing disc {existing_disc[0]}, track {existing_track[0]} "
                    f"vs. expected disc {disc}, track {track}. Skipping tagging."
                )
                continue
            else:
                logging.info(f"Existing tags in {flac_path} match generated values. Skipping update for those two fields.")
        else:
            if not existing_track:
                audio["tracknumber"] = track
            if not existing_disc:
                audio["discnumber"] = str(disc)

        audio["title"] = title

        try:
            audio.save()
            logging.info(f"Tagged successfully: {flac_path}")
        except Exception as e:
            logging.error(f"Error saving {flac_path}: {e}")

def parse_info_file(directory_path):
    """
    Given a directory path, finds the info file (assumed to be named in the format "base.shnid.txt"),
    reads it, and attempts to parse track entries for the FLAC files in the directory.

    This function supports four separate formats (handled in separate loops):

      1. New format with disc/set indicator:
         e.g., "d1t01. Tuning" or "s1t01. Tuning"
         Pattern: ^[ds](\d+)\s*t(\d+)[.\-]?\s+(.*)$
         (Disc and track numbers are read directly.)

      2. Format with no disc specified:
         e.g., "t01. Crowd"
         Pattern: ^t(\d+)[.\-]?\s+(.*)$
         (Assign a default disc value of 1.)

      3. Old format:
         e.g., "01. Tuning" or "1 Tuning"
         Pattern: ^\s*(\d+)(?:(?:[.\-]\s*)|\s+)(.*)$
         (Only a track number is provided; disc numbers are auto-assigned,
         with a reset to 1 (after the first entry) indicating a new disc.)

      4. New sNNN format:
         e.g., "s101. Tuning"
         Pattern: ^s(\d{3})[.\-]?\s+(.*)$
         In this case, use the three-digit number: the first digit is the disc number,
         and the last two digits form the track number.

    The function runs each loop separately and, if any one loop produces a result
    where the number of track entries equals the number of FLAC files and the tracks are in order,
    that result is used immediately. If none of the first three loops produce a valid result,
    a fourth (merged) loop is attempted. If a loop yields the correct number of entries,
    the remaining loops are skipped.

    The track-order check (tracks_in_order) is modified so that for entries with a disc value,
    track numbers must be consecutive starting at 1, and for entries where disc is not auto-assigned,
    the numbers must be strictly increasing.

    Returns:
        dict: Mapping from FLAC file full paths to a tuple (disc, track, title). For the sNNN format,
              disc is taken as the first digit and track is the remaining two digits.
    """


    # Get and sort FLAC files.
    #flac_files = glob(os.path.join(directory_path, "*.flac"))
    flac_files = glob(os.path.join(directory_path, "*.flac"))
    flac_files.sort(key=file_sort_key) #function handles cases where a number was no zero padded and there are more than 9 tracks in a disc. 
    #print(flac_files)
    #flac_files.sort(key=str.lower)
    n_files = len(flac_files)
    if n_files == 0:
        logging.error("No FLAC files found in the directory.")
        return {}

    # Identify the info file.
    info_files = [f for f in os.listdir(directory_path)
                  if f.endswith(".txt") and re.match(r"^[^.]+\.\d+\.txt$", f)]
    if not info_files:
        logging.error("No info file found in the directory.")
        return {}
    if len(info_files) > 1:
        logging.warning("Multiple info files found. Using the first one found.")
    info_file = info_files[0]
    info_file_path = os.path.join(directory_path, info_file)
    logging.info(f"Using info file: {info_file_path}")

    # Read nonempty lines.
    try:
        with open(info_file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        logging.error(f"Error reading info file {info_file_path}: {e}")
        return {}

    # Define the regex patterns.
    #new_pattern      = re.compile(r"^[ds](\d+)\s*t(\d+)[.\-]?\s+(.*)$", re.IGNORECASE)
    #new_pattern      = re.compile(r"^[ds](\d+)\s?t(\d+)[.\-]?\s+(.*)$", re.IGNORECASE)
    new_pattern       = re.compile(r"^[ds]\s*(\d+)\s*t\s*(\d+)[.\-]?\s+(.*)$", re.IGNORECASE)
    no_disc_pattern   = re.compile(r"^t(\d+)[.\-]?\s+(.*)$", re.IGNORECASE)
    old_pattern       = re.compile(r"^\s*(\d+)(?:(?:[.\-]\s*)|\s+)(.*)$")
    snnn_pattern      = re.compile(r"^s(\d{3})[.\-]?\s+(.*)$", re.IGNORECASE)

    # Helper: check track order.
    def tracks_in_order(entries):
        groups = {}
        for disc, track_str, title in entries:
            num = int(track_str)
            # Use disc as key; if disc is None, use a separate key.
            key = disc if disc is not None else "no_disc"
            groups.setdefault(key, []).append(num)
        #for group,item in groups.items():
        #    print(group,item)
        for key, numbers in groups.items():
            if key == "no_disc":
                for i in range(1, len(numbers)):
                    if numbers[i] <= numbers[i-1]:
                        return False
            else:
                numbers.sort()
                if numbers[0] != 1:
                    return False
                for i in range(1, len(numbers)):
                    #print(numbers[i], numbers[i-1])
                    if numbers[i] != numbers[i-1] + 1:
                        return False
        return True

    # Helper: try a given pattern.
    def try_pattern(pattern, auto_assign_disc=False):
        entries = []
        auto_disc = 1
        prev_auto_track = None
        for line in lines:
            m = pattern.match(line)
            if m:
                if pattern == new_pattern:
                    disc = int(m.group(1))
                    track = int(m.group(2))
                    title = m.group(3).strip()
                    title = clean_track_name(title)
                    entries.append((disc, f"{track:02d}", title))
                elif pattern == no_disc_pattern:
                    disc = 1
                    track = int(m.group(1))
                    title = m.group(2).strip()
                    title = clean_track_name(title)
                    entries.append((disc, f"{track:02d}", title))
                elif pattern == old_pattern:
                    track_number = int(m.group(1))
                    title = m.group(2).strip()
                    title = clean_track_name(title)
                    if auto_assign_disc:
                        if prev_auto_track is not None and track_number == 1:
                            auto_disc += 1
                        entries.append((auto_disc, f"{track_number:02d}", title))
                        prev_auto_track = track_number
                elif pattern == snnn_pattern:
                    # For sNNN, use the first digit as disc and the last two as track.
                    value = m.group(1)  # e.g., "101" or "212"
                    disc = int(value[0])
                    track = value[1:]   # already two digits
                    title = m.group(2).strip()
                    title = clean_track_name(title)
                    entries.append((disc, track, title))
        return entries

    # Try each pattern individually.
    patterns_to_try = [
        (new_pattern, False),
        (no_disc_pattern, False),
        (old_pattern, True),
        (snnn_pattern, False)
    ]
    for pat, auto_assign in patterns_to_try:
        track_entries = try_pattern(pat, auto_assign_disc=auto_assign)
        for entry in track_entries:
            print(entry)
        print(f"{pat=} {n_files=}")
        if track_entries and len(track_entries) == n_files and tracks_in_order(track_entries):
            logging.info(f"Pattern {pat.pattern} produced valid results.")
            mapping = {flac_files[i]: track_entries[i] for i in range(n_files)}
            return mapping

    # If none of the first loops yielded any results (i.e. all empty), don't perform a merged loop.
    if (not try_pattern(new_pattern) and not try_pattern(no_disc_pattern)
            and not try_pattern(old_pattern) and not try_pattern(snnn_pattern)):
        logging.error("None of the individual patterns produced any track entries.")
        return {}

    # Fourth (merged) loop: try each pattern in order on each line.
    track_entries = []
    auto_disc = 1
    prev_auto_track = None
    for line in lines:
        m = new_pattern.match(line)
        if m:
            disc = int(m.group(1))
            track = int(m.group(2))
            title = clean_track_name(m.group(3).strip())
            track_entries.append((disc, f"{track:02d}", title))
            continue
        m = no_disc_pattern.match(line)
        if m:
            disc = 1
            track = int(m.group(1))
            title = clean_track_name(m.group(2).strip())
            track_entries.append((disc, f"{track:02d}", title))
            continue
        m = old_pattern.match(line)
        if m:
            track_number = int(m.group(1))
            title = clean_track_name(m.group(2).strip())
            if prev_auto_track is not None and track_number == 1:
                auto_disc += 1
            track_entries.append((auto_disc, f"{track_number:02d}", title))
            prev_auto_track = track_number
            continue
        m = snnn_pattern.match(line)
        if m:
            value = m.group(1)
            disc = int(value[0])
            track = value[1:]
            title = clean_track_name(m.group(2).strip())
            track_entries.append((disc, track, title))
            continue
    b_inorder = tracks_in_order(track_entries)
    if track_entries and len(track_entries) == n_files and b_inorder:
        logging.info("Merged pattern produced valid results.")
        mapping = {flac_files[i]: track_entries[i] for i in range(n_files)}
        return mapping
    else:
        error_message = "Error:"
        if len(track_entries) != n_files:
            error_message = error_message + f"Number of track entries ({len(track_entries)}) does not match number of FLAC files ({n_files}). "
        if not b_inorder:
            error_message = error_message + f"Tracks are not in order. "
        print(track_entries)
        logging.error(error_message)
        raise ValueError(error_message)


def add_line_numbers(file_path):
    """
    Reads the file at file_path and adds a zero-padded (2-digit) sequential number,
    followed by a period and a space, to the beginning of each nonempty line.
    
    The file is then overwritten with the modified lines.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        logging.error(f"Error reading {file_path}: {e}")
        return

    new_lines = []
    counter = 1
    for line in lines:
        if line.strip():
            new_line = f"{counter:02d}. {line}"
            counter += 1
        else:
            new_line = line
        new_lines.append(new_line)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        logging.info(f"Line numbers added to {file_path}")
    except Exception as e:
        logging.error(f"Error writing to {file_path}: {e}")

def tag_flac_files_wrapper(track_mapping):
    """
    Wrapper to log the mapping before tagging.
    """
    for flac_path, (disc, track, title) in track_mapping.items():
        logging.info(f"File: {flac_path} -> Disc {disc}, Track {track}: {title}")
    tag_flac_files(track_mapping)



def all_flac_tagged(directory):
    """
    Checks all FLAC files in the given directory (non-recursively) to ensure each file
    has non-empty 'tracknumber' and 'title' tags.

    Returns:
        True if every FLAC file is tagged with both tracknumber and title,
        False otherwise.
    """
    flac_files = glob(os.path.join(directory, "*.flac"))
    if not flac_files:
        # If there are no FLAC files, we assume "all" are tagged.
        return True

    for flac_file in flac_files:
        try:
            audio = FLAC(flac_file)
        except Exception as e:
            print(f"Error loading {flac_file}: {e}")
            return False

        # Check that the tracknumber tag exists and is non-empty.
        track = audio.get("tracknumber")
        if not track or not track[0].strip():
            print(f"Missing or empty 'tracknumber' tag in {flac_file}")
            return False

        # Check that the title tag exists and is non-empty.
        title = audio.get("title")
        if not title or not title[0].strip():
            print(f"Missing or empty 'title' tag in {flac_file}")
            return False

    return True


def main():
    logging.basicConfig(
        level=logging.INFO,
        #filename='Tagging.log',
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("flac_tagging.log"),
            logging.StreamHandler()
        ]
    )
    
    parser = argparse.ArgumentParser(description="Process FLAC files and their track info.")
    parser.add_argument("directory", help="Directory containing the FLAC files and the info file.")
    parser.add_argument("--add-line-numbers", help="Optional: File path for which to add sequential line numbers.", default=None)
    
    args = parser.parse_args()
    directory = args.directory

    if not os.path.isdir(directory):
        logging.error(f"{directory} is not a valid directory.")
        return

    if args.add_line_numbers:
        add_line_numbers(args.add_line_numbers)
    if not all_flac_tagged(directory): #don't bother if it is tagged
        try:
            track_mapping = parse_info_file(directory)
        except ValueError as e:
            logging.error(e)
            return

        tag_flac_files_wrapper(track_mapping)
    else:
        logging.info(f"Files are already tagged in {directory}")




def clear_title_tag_in_folder(directory_path):
    """
    Clears the 'title' tag from all FLAC files in the specified folder.
    For each file, if a "title" tag is present, it is removed and the file is saved.

    :param directory_path: The path to the folder containing FLAC files.
    """
    if not os.path.isdir(directory_path):
        print(f"Directory '{directory_path}' does not exist.")
        return

    # Get list of all FLAC files in the folder (non-recursive)
    flac_files = glob(os.path.join(directory_path, "*.flac"))
    
    if not flac_files:
        print("No FLAC files found in the directory.")
        return

    for flac_file in flac_files:
        try:
            audio = FLAC(flac_file)
            if 'title' in audio:
                del audio['title']
                audio.save()
                print(f"Cleared title tag from: {flac_file}")
            else:
                print(f"No title tag found in: {flac_file}")
        except Exception as e:
            print(f"Error processing {flac_file}: {e}")



if __name__ == "__main__":
    import sys
    from pathlib import Path
    dirname = r"M:\To_Tag\gd1960s"
    needfixing = []
    folderlist = [Path(f).as_posix() for f in os.scandir(dirname) if f.is_dir()]
    #folderlist = [r'X:\Downloads\_FTP\gdead.1990.project\gd1990-07-19.147777.sbd-UltraMatrix-cm.pearson.miller.t-flac16' ]
    #folderlist = read_file_to_list()
    for fldr in folderlist:
        sys.argv = [
            "flac_tagging.py",                 # script name (dummy)
            #
            fldr
            #"--add-line-numbers", "/path/to/your/textfile.txt"  # optional argument
        ]
        #clear_title_tag_in_folder(fldr)
        clear_title_tag_in_folder(fldr)
        main()
        if not all_flac_tagged(fldr) and len(folderlist) > 1:
            needfixing.append(fldr)

    for x in needfixing:
        #stick these at the end of the log and also print them separately below
        logging.error(f"no tags in {x}" )

    if needfixing:
        print('The following folders need investigation:')        
    for x in needfixing:
        #print missing tag folders
        print(x)
    print(f'#Summary. Folders Processed: {len(folderlist)}  Untagged Folder Count: {len(needfixing)}')
