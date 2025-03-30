"""
#!/usr/bin/env python3
This script processes FLAC files and their associated track info files to tag the FLAC files with metadata.
It includes functions for validating dates, sorting files, cleaning track names, stripping text after a certain number of spaces,
tagging FLAC files, parsing info files, adding line numbers to files, checking if all FLAC files are tagged, and clearing specific tags.
Functions:
- is_valid_date(date_str): Checks if a given string is a valid date in various formats.
- file_sort_key(filepath): Generates a sorting key for FLAC files based on disc and track numbers.
- clean_track_name(title): Cleans a track title by removing unwanted patterns and characters.
- strip_after_n_spaces(s, n): Returns the substring of s up to the first occurrence of n or more consecutive whitespace characters.
- tag_flac_files(track_mapping): Tags FLAC files using a given track mapping dictionary.
- parse_info_file(directory_path): Parses an info file in a given directory to extract track entries for FLAC files.
- add_line_numbers(file_path): Adds sequential line numbers to each nonempty line in a file.
- tag_flac_files_wrapper(track_mapping): Wrapper function to log the mapping before tagging FLAC files.
- all_flac_tagged(directory): Checks if all FLAC files in a directory have non-empty 'tracknumber' and 'title' tags.
- clear_title_tag_in_folder(directory_path): Clears the 'title' tag from all FLAC files in a specified folder.
- clear_song_specific_tags_in_folder(directory_path): Clears the 'title', 'tracknumber', and 'discnumber' tags from all FLAC files in a specified folder.
- read_file_to_list(file_name): Reads a text file and returns a list of its lines.
The script can be run as a standalone program, processing a specified directory of FLAC files and their info file.
"""
import os
import re
#import argparse
import logging
from glob import glob
from mutagen.flac import FLAC
from datetime import datetime


def is_valid_date(date_str):
    """
    Check if the provided string is a valid date in any of the specified formats.

    Args:
        date_str (str): The date string to validate.

    Returns:
        bool: True if the date string matches any of the specified formats, False otherwise.

    Logs:
        Logs a message indicating the date string that was found and skipped if it matches any format.
    """
    formats = ['%y-%m-%d', '%Y-%m-%d', '%m-%d-%Y', '%m-%d-%y','%y.%m.%d', '%Y.%m.%d', '%m.%d.%Y', '%m.%d.%y'
               ,'%y/%m/%d', '%Y/%m/%d', '%m/%d/%Y', '%m/%d/%y']
    #print(f'{date_str=}')
    for fmt in formats:
        try:
            dateval =  datetime.strptime(date_str, fmt)
        except ValueError:
            continue
        if dateval:
            print(f'Date Found, skipping line: "{date_str}"')
            logging.info(f'Date Found, skipping line: "{date_str}"')
            return True
    return False  # or raise an exception if preferred
    

def file_sort_key(filepath):
    """
    Generate a sorting key for a given file path based on disc and track numbers.
    The function extracts disc and track numbers from the file name using a regular expression.
    The expected format in the file name is either 'd<disc_number>t<track_number>' or 's<disc_number>t<track_number>',
    where <disc_number> and <track_number> are integers.
    If the disc and track numbers are found, the function returns a tuple (disc, track).
    If the pattern is not found, it returns a tuple (float('inf'), base.lower()), where 'base' is the base name of the file.
    Args:
        filepath (str): The path to the file.
    Returns:
        tuple: A tuple containing the disc and track numbers if found, otherwise (float('inf'), base.lower()).
    """
    base = os.path.splitext(os.path.basename(filepath))[0]
    m = re.search(r"[ds](\d+)[tT](\d+)", base, re.IGNORECASE)
    #m = re.search(r"[ds](\d+)[tT](\d+)$", base, re.IGNORECASE)
    if m:
        disc = int(m.group(1))
        track = int(m.group(2))
        print(filepath,disc,track)
        return (disc, track)
        
    else:
        print(filepath)
        return (float('inf'), base.lower())


def clean_track_name(title):
    """
    Cleans up a track name by performing various substitutions and removals.
    The function performs the following operations on the input title:
    1. Strips content after a certain number of spaces.
    2. Removes oddball whitespace characters (tabs, newlines, etc.).
    3. Trims multiple spaces down to a single space.
    4. Removes content within square brackets.
    5. Removes content within curly braces.
    6. Removes time patterns within parentheses (e.g., "06:03" or "06:03.667").
    7. Removes standalone time patterns (e.g., "06:03" or "06:03.667").
    8. Removes asterisk, semicolon, and percent characters.
    9. Removes leading "->" or ">" with optional whitespace.
    10. Removes "encore" related text unless it contains "encore break".
    11. Removes leading "e:" with optional whitespace.
    12. Removes leading dashes.
    13. Ensures ">" is preceded and followed by a space if not already followed by whitespace or end-of-string.
    14. Strips leading and trailing whitespace.
    Args:
        title (str): The original track name to be cleaned.
    Returns:
        str: The cleaned track name. If the cleaned name is empty, returns the original title.
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
    title = title.replace(';', '')
    title = title.replace('%', '')
    # Remove a leading "->" or ">" with optional whitespace.
    title = re.sub(r'^\s*(->|>)\s*', '', title)
    #Encore
    if 'encore break' not in title.lower():
        title = re.sub(r"^encore:?\s*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"[\(\[]\s*encore\s*[\)\]]", "", title, flags=re.IGNORECASE)
    title = re.sub(r'^\s*e:\s*', '', title, flags=re.IGNORECASE)
    #get rid of leading dashes:
    title = re.sub(r'^\s*-\s*', '', title)
    # Ensure ">" is preceded by a space.
    title = title.replace('--', '-')
    title = title.replace('->', '>')
    title = re.sub(r'(?<!\s)>', ' >', title)
    # Ensure ">" is followed by a space if not already followed by whitespace or end-of-string.
    title = re.sub(r'>(?!\s|$)', '> ', title)    
    # Strip leading/trailing whitespace.
    cleaned = title.strip()
    return cleaned if cleaned else original


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


def tag_flac_files(track_mapping):
    """
    Tags FLAC files with the provided track information.
    Args:
        track_mapping (dict): A dictionary where the keys are file paths to FLAC files and the values are tuples 
                              containing disc number, track number, and title.
    The function performs the following steps:
    1. Logs the start of tagging for each file.
    2. Attempts to load the FLAC file.
    3. Checks for existing track and disc numbers in the file's metadata.
    4. If existing tags are found and they do not match the provided values, logs an error and skips tagging.
    5. If existing tags match or are not present, updates the track number, disc number, and title.
    6. Saves the updated metadata back to the file.
    7. Logs the success or failure of the tagging operation.
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
    Args:
        directory_path (str): The path to the directory containing the FLAC and info files.
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
    #info_files = [f for f in os.listdir(directory_path)
    #              if f.endswith(".txt") and re.match(r"^[^.]+\.\d+\.txt$", f)]
    #if not info_files:
     #   logging.warning("No info file with shnid found in the directory, checking for a txt file")
    info_files = [f for f in os.listdir(directory_path)
                    if f.lower().endswith(".txt")]    
    # print('-------------------------------------------------------------------------------')
    # for info in info_files:
    #     print(info)
    if not info_files:
        logging.error("No info file found in the directory.")
        return {}
    #if len(info_files) > 1:
    #    logging.warning("Multiple info files found. Using the first one found.")
    info_file_cnt = len(info_files)
    curr_infofile = 0
    for info_file in info_files:
        curr_infofile = curr_infofile + 1
        #info_file = info_files[0]
        try:
            info_file_path = os.path.join(directory_path, info_file)
            logging.info(f"Using info file: {info_file_path}")

        # Read nonempty lines.
        
            try:
                #with open(info_file_path, "r", encoding="utf-8") as f:
                #lines = [line.strip() for line in f if line.strip()]
                    for enc in ['utf-8', 'cp1252', 'latin1', 'utf-16']:
                        try:
                            with open(info_file_path, "r", encoding=enc) as f:
                                lines = [line.strip() for line in f if line.strip()]
                            print(f"Successfully read with encoding: {enc}")
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        print("Failed to decode the file with the attempted encodings.")                
                    
                    #lines = [line.strip() for line in content if line.strip()]
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
            # def tracks_in_order(entries):
            #     groups = {}
            #     for disc, track_str, title in entries:
            #         num = int(track_str)
            #         # Use disc as key; if disc is None, use a separate key.
            #         key = disc if disc is not None else "no_disc"
            #         groups.setdefault(key, []).append(num)
            #     #for group,item in groups.items():
            #     #    print(group,item)
            #     for key, numbers in groups.items():
            #         if key == "no_disc":
            #             for i in range(1, len(numbers)):
            #                 if numbers[i] <= numbers[i-1]:
            #                     for number in numbers:
            #                         print(f'{number=}')                        
            #                     return False
            #         else:
            #             numbers.sort()
            #             if numbers[0] != 1:
            #                 for number in numbers:
            #                     print(f'{number=}')                    
            #                 return False
            #             for i in range(1, len(numbers)):
            #                 #print(numbers[i], numbers[i-1])
            #                 if numbers[i] != numbers[i-1] + 1:
            #                     for number in numbers:
            #                         print(f'{number=}')
            #                     return False
            #     return True
            def tracks_in_order(entries):
                """
                Checks that the list of entries (each a tuple: (disc, track_str, title))
                satisfies one of two conditions:
                
                Condition 1: For each disc (when disc is not None), track numbers are consecutive starting at 1.
                Condition 2: When sorted by disc and track number, the overall track numbers are strictly increasing.
                
                Returns True if either condition is met, and False otherwise.
                """
                # Condition 1: Check per-disc consecutive order.
                condition1 = True
                groups = {}
                for disc, track_str, title in entries:
                    # Group by disc. Note: if disc is None, treat it as a separate group.
                    groups.setdefault(disc, []).append(int(track_str))
                for disc, numbers in groups.items():
                    # For disc groups where disc is not None, enforce that numbering starts at 1 and is consecutive.
                    if disc is not None:
                        numbers.sort()
                        if numbers[0] != 1:
                            condition1 = False
                            break
                        for i in range(1, len(numbers)):
                            if numbers[i] != numbers[i - 1] + 1:
                                condition1 = False
                                break
                        if not condition1:
                            break
                    else:
                        # If disc is None, we do not enforce the "start at 1" rule in Condition 1.
                        # (You might consider that a failure of condition1 if you expect disc always to be set.)
                        condition1 = False
                        break

                # Condition 2: Check that overall track numbers are strictly increasing
                sorted_entries = sorted(
                    entries,
                    key=lambda x: ((int(x[0]) if x[0] is not None else 0), int(x[1]))
                )
                condition2 = True
                for i in range(1, len(sorted_entries)):
                    prev = int(sorted_entries[i - 1][1])
                    curr = int(sorted_entries[i][1])
                    if curr <= prev:
                        condition2 = False
                        break

                return condition1 or condition2

            # Helper: try a given pattern.
            def try_pattern(pattern, auto_assign_disc=False):
                entries = []
                auto_disc = 1
                prev_auto_track = None
                for line in lines:
                    if 'discs audio' in line.lower():
                        continue
                    if line.strip().lower() in ('24 bit', '16 bit') or line.strip().lower().startswith('16-bit') or line.strip().lower().startswith('24-bit'):
                        continue
                    if is_valid_date(line.split()[0].strip()):
                        continue
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
                    #if len(entries) == len(flac_files):
                    #    break
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
                if info_file_cnt == curr_infofile:
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
                #if len(track_entries) == len(flac_files):
                #    break        
            b_inorder = tracks_in_order(track_entries)
            if track_entries and len(track_entries) == n_files and b_inorder:
                logging.info("Merged pattern produced valid results.")
                mapping = {flac_files[i]: track_entries[i] for i in range(n_files)}
                return mapping
            else:
                logging.error(f'Problem in {curr_infofile}:')
                error_message = "Error:"
                if len(track_entries) != n_files:
                    error_message = error_message + f"Number of track entries ({len(track_entries)}) does not match number of FLAC files ({n_files}). "
                if not b_inorder:
                    error_message = error_message + "Tracks are not in order. "
                    for track in track_entries:
                        print (track)
                #print(track_entries)
                logging.error(error_message)
                if info_file_cnt == curr_infofile:
                    raise ValueError(error_message)
        except Exception as e:
            print(f'Error: {e}')
            logging.error({e} in {info_file})

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


def tag_folder(directory:str, add_line_numbers:str=None):
    """
    Main function to process FLAC files and their track info.
    This function sets up logging, parses command-line arguments, and processes
    the specified directory containing FLAC files and an info file. It can also
    optionally add sequential line numbers to a specified file.
    Command-line arguments:
    directory (str): Directory containing the FLAC files and the info file.
    --add-line-numbers (str, optional): File path for which to add sequential line numbers.
    The function performs the following steps:
    1. Sets up logging to both a file and the console.
    2. Parses command-line arguments.
    3. Checks if the specified directory is valid.
    4. Optionally adds line numbers to a specified file.
    5. Checks if all FLAC files in the directory are already tagged.
    6. If not tagged, parses the info file to get track mapping.
    7. Tags the FLAC files based on the track mapping.
    Returns:
    None
    """
    logging.basicConfig(
        level=logging.INFO,
        #filename='Tagging.log',
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("flac_tagging.log"),
            logging.StreamHandler()
        ]
    )
    
    #parser = argparse.ArgumentParser(description="Process FLAC files and their track info.")
    #parser.add_argument("directory", help="Directory containing the FLAC files and the info file.")
    #parser.add_argument("--add-line-numbers", help="Optional: File path for which to add sequential line numbers.", default=None)
    
    #args = parser.parse_args()
    #directory = args.directory

    if not os.path.isdir(directory):
        logging.error(f"{directory} is not a valid directory.")
        return

    if add_line_numbers:
        add_line_numbers(add_line_numbers)
    if not all_flac_tagged(directory): #don't bother if it is tagged
        try:
            track_mapping = parse_info_file(directory)
        except ValueError as e:
            logging.error(e)
            return
        if track_mapping:
            tag_flac_files_wrapper(track_mapping)
        else:
            logging.error(f"No Track Mapping for {directory}")
    else:
        logging.info(f"Files are already tagged in {directory}")

    return all_flac_tagged(directory)


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

def clear_song_specific_tags_in_folder(directory_path):
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
            if 'title' in audio or 'tracknumber' in audio or 'discnumber' in audio:
                if 'title' in audio:
                    del audio['title']
                    print(f"Cleared title tag from: {flac_file}")
                else:
                    print(f"No title tag found in: {flac_file}")
                if 'tracknumber' in audio:
                    del audio['tracknumber']
                    print(f"Cleared tracknumber tag from: {flac_file}")
                else:
                    print(f"No tracknumber tag found in: {flac_file}")  
                if 'discnumber' in audio:
                    del audio['discnumber']
                    print(f"Cleared discnumber tag from: {flac_file}")
                else:
                    print(f"No discnumber tag found in: {flac_file}")                                                          
                audio.save()
            else:
                print(f'No title, disc, or tracknumber tags found in: {flac_file}')
        except Exception as e:
            print(f"Error processing {flac_file}: {e}")

            # if not existing_track:
            #     audio["tracknumber"] = track
            # if not existing_disc:
            #     audio["discnumber"] = str(disc)

def read_file_to_list(file_name):
    """
    Reads the specified text file and returns a list of its lines.
    If the file name is a relative path, it's assumed to be relative to the current working directory.

    :param file_name: The path to the text file (relative or absolute).
    :return: A list of strings, where each string is a line from the file.
    """
    if not os.path.isabs(file_name):
        file_path = os.path.join(os.getcwd(), file_name)
    else:
        file_path = file_name

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        return lines
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []

if __name__ == "__main__":
    from pathlib import Path
    #dirname = r"X:/Downloads/_FTP/gdead.9999.updates/"
    needfixing = []
    #folderlist = [Path(f).as_posix() for f in os.scandir(dirname) if f.is_dir()]
    folderlist = [
          r"X:\Downloads\_Extract\Neil Young\Neil Young Archives Concerts\1969-10-16 Canterbury, Ann Arbor (NYA) TC\Neil Young 10.16.69 3rd Set"
         ]
    #folderlist = read_file_to_list('untaggged_list.txt')
    for fldr in folderlist:
        fldr = Path(fldr).as_posix().strip()
        # sys.argv = [
        #     "flac_tagging.py",                 # script name (dummy)
        #     #
        #     fldr.strip()
        #     #"--add-line-numbers", "/path/to/your/textfile.txt"  # optional argument
        # ]
        clear_song_specific_tags_in_folder(fldr)
        #clear_title_tag_in_folder(fldr)
        folder_only = Path(fldr).name
        print(f'{folder_only}')
            #problem_folders.append(folder_only)
        #if shnid:
        #    save_text_file(shnid,fldr)          
        tag_folder(fldr)
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
