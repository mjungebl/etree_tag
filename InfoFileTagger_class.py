#!/usr/bin/env python3
"""
FLAC tagging utility.

Encapsulates parsing of "info" text files, cleanup of track titles, and tagging FLACs
with disc/track/title using mutagen. Supports multiple common list formats:
 - d1t01. Title / s1t01. Title
 - t01. Title         (assumes disc=1)
 - 01. Title          (auto-assigns discs when track resets to 1)
 - s101. Title        (first digit=disc, last two=track)

"""

from __future__ import annotations

import os
import re
import logging
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from datetime import datetime
from mutagen.flac import FLAC

TrackEntry = Tuple[int, str, str]  # (disc, track_as_2char_str, title)
TrackMapping = Dict[str, TrackEntry]  # flac_path -> (disc, track, title)


class FlacInfoFileTagger:
    """
    Class wrapper around FLAC tagging helpers.

    Typical usage:
        tagger = FlacInfoFileTagger(log_to_file="flac_tagging.log")
        tagger.tag_folder(r"X:/Downloads/_FTP/_Concerts_Unofficial/_renamed2/Phil/phil2005-05-15.90639")

    You can also call granular methods:
        mapping = tagger.parse_info_file(folder)
        tagger.tag_flac_files(mapping)
    """

    # -----------------------
    # Construction / Logging
    # -----------------------
    def __init__(
        self,
        strip_after_space_count: int = 5,
        logger: Optional[logging.Logger] = None,
        log_level: int = logging.INFO,
        log_to_file: Optional[str] = None,
        also_log_to_console: bool = True,
    ) -> None:
        """
        Args:
            strip_after_space_count: Cut off titles after N consecutive spaces.
            logger: Provide a pre-configured logger (optional).
            log_level: Default logging level if we configure logging.
            log_to_file: If set, write logs to this file.
            also_log_to_console: If True, attach a StreamHandler to console.
        """
        self.strip_after_space_count = strip_after_space_count

        if logger is not None:
            self.log = logger
        else:
            self.log = logging.getLogger(self.__class__.__name__)
            self.log.setLevel(log_level)
            # Avoid duplicate handlers if multiple instances constructed
            if not self.log.handlers:
                handlers: List[logging.Handler] = []
                if log_to_file:
                    handlers.append(logging.FileHandler(log_to_file))
                if also_log_to_console:
                    handlers.append(logging.StreamHandler())
                if handlers:
                    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
                    for h in handlers:
                        h.setFormatter(fmt)
                        self.log.addHandler(h)

        # Compile patterns once
        self._pat_new = re.compile(
            r"^[ds]\s*(\d+)\s*t\s*(\d+)[.\-]?\s+(.*)$", re.IGNORECASE
        )
        self._pat_no_disc = re.compile(r"^t(\d+)[.\-]?\s+(.*)$", re.IGNORECASE)
        self._pat_old = re.compile(r"^\s*(\d+)(?:(?:[.\-]\s*)|\s+)(.*)$")
        self._pat_snnn = re.compile(r"^s(\d{3})[.\-]?\s+(.*)$", re.IGNORECASE)

        # Date formats to ignore as "header lines"
        self._date_formats = [
            "%y-%m-%d",
            "%Y-%m-%d",
            "%m-%d-%Y",
            "%m-%d-%y",
            "%y.%m.%d",
            "%Y.%m.%d",
            "%m.%d.%Y",
            "%m.%d.%y",
            "%y/%m/%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%m/%d/%y",
        ]

    # -----------------------
    # Static / Utility
    # -----------------------
    @staticmethod
    def read_file_to_list(file_name: str) -> List[str]:
        """
        Reads a text file and returns list of lines (no newline chars).
        """
        file_path = (
            file_name
            if os.path.isabs(file_name)
            else os.path.join(os.getcwd(), file_name)
        )
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().splitlines()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

    @staticmethod
    def file_sort_key(filepath: str) -> Tuple[int, int] | Tuple[float, str]:
        """
        Sort key for FLAC paths using dNNtNN / sNNtNN in basename; fallback alphabetical.
        """
        base = os.path.splitext(os.path.basename(filepath))[0]
        m = re.search(r"[ds](\d+)[tT](\d+)", base, re.IGNORECASE)
        if m:
            disc = int(m.group(1))
            track = int(m.group(2))
            return (disc, track)
        return (float("inf"), base.lower())

    def is_valid_date(self, token: str) -> bool:
        """
        True if token matches any supported date format (and logs once).
        """
        for fmt in self._date_formats:
            try:
                dt = datetime.strptime(token, fmt)
            except ValueError:
                continue
            if dt:
                self.log.info(f'Date Found, skipping line: "{token}"')
                return True
        return False

    def strip_after_n_spaces(self, s: str, n: Optional[int] = None) -> str:
        """
        Truncate s before the first occurrence of N consecutive spaces (if truncation non-empty).
        """
        n = n or self.strip_after_space_count
        m = re.search(rf"\s{{{n},}}", s)
        if m:
            idx = m.start()
            if idx > 0:
                result = s[:idx].rstrip()
                if result:
                    return result
        return s

    def clean_track_name(self, title: str) -> str:
        """
        Normalize a track title with the same rules as the original script (with a few fixes).
        """
        original = title
        title = self.strip_after_n_spaces(title, self.strip_after_space_count)

        # These were missing assignment in the original code
        title = re.sub(r"[\t\n\r\f\v]+", " ", title)
        title = re.sub(r" {2,}", " ", title)

        title = re.sub(r"\[.*?\]", "", title)  # [brackets]
        title = re.sub(r"\{.*?\}", "", title)  # {braces}
        title = re.sub(
            r"\(\s*\d{1,2}:\d{2}(?:\.\d{1,3})?\s*\)", "", title
        )  # (mm:ss[.sss])
        title = re.sub(r"\b\d{1,2}:\d{2}(?:\.\d{1,3})?\b", "", title)  # mm:ss[.sss]
        title = title.replace("*", "").replace(";", "").replace("%", "")
        title = re.sub(r"^\s*(->|>)\s*", "", title)  # leading -> or >

        if "encore break" not in title.lower():
            title = re.sub(r"^encore:?\s*", "", title, flags=re.IGNORECASE)
            title = re.sub(r"[\(\[]\s*encore\s*[\)\]]", "", title, flags=re.IGNORECASE)
        title = re.sub(r"^\s*e:\s*", "", title, flags=re.IGNORECASE)

        title = re.sub(r"^\s*-\s*", "", title)  # leading dashes
        title = title.replace("--", "-").replace("->", ">")
        title = re.sub(r"(?<!\s)>", " >", title)  # space before >
        title = re.sub(r">(?!\s|$)", "> ", title)  # space after >

        cleaned = title.strip()
        return cleaned if cleaned else original

    # -----------------------
    # Core tagging operations
    # -----------------------
    def tag_flac_files(self, track_mapping: TrackMapping) -> None:
        """
        Tag each FLAC file with disc/track/title.

        If 'tracknumber' and 'discnumber' already exist and do NOT match expected,
        the file is skipped and an error is logged (preserves existing intentional tags).
        """
        for flac_path, (disc, track, title) in track_mapping.items():
            self.log.info(
                f"Tagging file: {flac_path} -> Disc {disc}, Track {track}: {title}"
            )
            try:
                audio = FLAC(flac_path)
            except Exception as e:
                self.log.error(f"Error loading {flac_path}: {e}")
                continue

            existing_track = audio.get("tracknumber")
            existing_disc = audio.get("discnumber")

            if existing_track and existing_disc:
                if existing_track[0] != track or existing_disc[0] != str(disc):
                    self.log.error(
                        f"Mismatch in {flac_path}: existing disc {existing_disc[0]}, track {existing_track[0]} "
                        f"vs. expected disc {disc}, track {track}. Skipping tagging."
                    )
                    continue
                else:
                    self.log.info(
                        "Existing disc/track match expected; leaving those untouched."
                    )

            if not existing_track:
                audio["tracknumber"] = track
            if not existing_disc:
                audio["discnumber"] = str(disc)

            audio["title"] = title

            try:
                audio.save()
                self.log.info(f"Tagged successfully: {flac_path}")
            except Exception as e:
                self.log.error(f"Error saving {flac_path}: {e}")

    def tag_flac_files_wrapper(self, track_mapping: TrackMapping) -> None:
        for flac_path, (disc, track, title) in track_mapping.items():
            self.log.info(f"File: {flac_path} -> Disc {disc}, Track {track}: {title}")
        self.tag_flac_files(track_mapping)

    def all_flac_tagged(self, directory: str) -> bool:
        """
        True iff every *.flac (non-recursive) in directory has non-empty tracknumber and title.
        """
        flacs = glob(os.path.join(directory, "*.flac"))
        if not flacs:
            # If there are no FLAC files, treat as "nothing to tag" = True
            return True

        for fp in flacs:
            try:
                audio = FLAC(fp)
            except Exception as e:
                print(f"Error loading {fp}: {e}")
                return False

            track = audio.get("tracknumber")
            if not track or not track[0].strip():
                print(f"Missing or empty 'tracknumber' tag in {fp}")
                return False

            title = audio.get("title")
            if not title or not title[0].strip():
                print(f"Missing or empty 'title' tag in {fp}")
                return False

        return True

    # -----------------------
    # Parsing "info" files
    # -----------------------
    def _tracks_in_order(
        self, entries: List[TrackEntry | Tuple[Optional[int], str, str]]
    ) -> bool:
        """
        Pass if either:
          1) per disc, tracks are consecutive starting at 1, or
          2) overall strictly increasing track numbers when sorted by (disc, track).
        """
        # Condition 1
        condition1 = True
        groups: Dict[Optional[int], List[int]] = {}
        for disc, track_str, _ in entries:
            groups.setdefault(disc, []).append(int(track_str))
        for disc, numbers in groups.items():
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
                condition1 = False
                break

        # Condition 2
        sorted_entries = sorted(
            entries, key=lambda x: ((int(x[0]) if x[0] is not None else 0), int(x[1]))
        )
        condition2 = True
        for i in range(1, len(sorted_entries)):
            if int(sorted_entries[i][1]) <= int(sorted_entries[i - 1][1]):
                condition2 = False
                break

        return condition1 or condition2

    def parse_info_file(self, directory_path: str) -> TrackMapping:
        """
        Find a .txt file in directory and parse lines into (disc, track, title) entries,
        trying multiple formats. Returns mapping matching the number/order of *.flac files.
        """
        # Collect and sort flacs using the filename key
        flac_files = glob(os.path.join(directory_path, "*.flac"))
        flac_files.sort(key=self.file_sort_key)
        n_files = len(flac_files)
        if n_files == 0:
            self.log.error("No FLAC files found in the directory.")
            return {}

        # Discover candidate info files
        info_files = [
            f for f in os.listdir(directory_path) if f.lower().endswith(".txt")
        ]
        if not info_files:
            self.log.error("No info file found in the directory.")
            return {}

        def try_read_lines(fp: str) -> Optional[List[str]]:
            # Try a few encodings
            for enc in ["utf-8", "cp1252", "latin1", "utf-16"]:
                try:
                    with open(fp, "r", encoding=enc) as f:
                        lines = [ln.strip() for ln in f if ln.strip()]
                    self.log.info(f"Read info file '{fp}' with encoding {enc}")
                    return lines
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    self.log.error(f"Error reading {fp}: {e}")
                    return None
            self.log.error(f"Failed to decode {fp} with attempted encodings.")
            return None

        def try_pattern(
            pattern: re.Pattern, lines: Sequence[str], auto_assign_disc: bool = False
        ) -> List[TrackEntry]:
            entries: List[TrackEntry] = []
            auto_disc = 1
            prev_auto_track: Optional[int] = None

            for line in lines:
                lo = line.lower().strip()
                if "discs audio" in lo:
                    continue
                if lo in ("24 bit", "16 bit") or lo.startswith(
                    ("16-bit", "24-bit", "16bit", "24bit", "24 bit/44.1", "16 bit/44.1")
                ):
                    continue
                # skip if first token is a date
                first_tok = line.split()[0] if line.split() else ""
                if first_tok and self.is_valid_date(first_tok):
                    continue

                m = pattern.match(line)
                if not m:
                    continue

                if pattern is self._pat_new:
                    disc = int(m.group(1))
                    track = int(m.group(2))
                    title = self.clean_track_name(m.group(3).strip())
                    entries.append((disc, f"{track:02d}", title))
                elif pattern is self._pat_no_disc:
                    disc = 1
                    track = int(m.group(1))
                    title = self.clean_track_name(m.group(2).strip())
                    entries.append((disc, f"{track:02d}", title))
                elif pattern is self._pat_old:
                    track_number = int(m.group(1))
                    title = self.clean_track_name(m.group(2).strip())
                    if auto_assign_disc:
                        if prev_auto_track is not None and track_number == 1:
                            auto_disc += 1
                        entries.append((auto_disc, f"{track_number:02d}", title))
                        prev_auto_track = track_number
                elif pattern is self._pat_snnn:
                    value = m.group(1)  # e.g., "101"
                    disc = int(value[0])
                    track = value[1:]
                    title = self.clean_track_name(m.group(2).strip())
                    entries.append((disc, track, title))

            return entries

        patterns_to_try = [
            (self._pat_new, False),
            (self._pat_no_disc, False),
            (self._pat_old, True),
            (self._pat_snnn, False),
        ]

        for info_file in info_files:
            info_path = os.path.join(directory_path, info_file)
            lines = try_read_lines(info_path)
            if not lines:
                continue

            # Try each pattern independently
            for pat, auto_flag in patterns_to_try:
                entries = try_pattern(pat, lines, auto_assign_disc=auto_flag)
                if (
                    entries
                    and len(entries) == n_files
                    and self._tracks_in_order(entries)
                ):
                    self.log.info(f"Pattern {pat.pattern} produced valid results.")
                    return {flac_files[i]: entries[i] for i in range(n_files)}

            # If none produced a full set, attempt merged pass
            merged: List[TrackEntry] = []
            auto_disc = 1
            prev_auto_track: Optional[int] = None

            for line in lines:
                # Try in order: new -> no_disc -> old -> snnn
                m = self._pat_new.match(line)
                if m:
                    disc = int(m.group(1))
                    track = int(m.group(2))
                    title = self.clean_track_name(m.group(3).strip())
                    merged.append((disc, f"{track:02d}", title))
                    continue

                m = self._pat_no_disc.match(line)
                if m:
                    disc = 1
                    track = int(m.group(1))
                    title = self.clean_track_name(m.group(2).strip())
                    merged.append((disc, f"{track:02d}", title))
                    continue

                m = self._pat_old.match(line)
                if m:
                    tn = int(m.group(1))
                    title = self.clean_track_name(m.group(2).strip())
                    if prev_auto_track is not None and tn == 1:
                        auto_disc += 1
                    merged.append((auto_disc, f"{tn:02d}", title))
                    prev_auto_track = tn
                    continue

                m = self._pat_snnn.match(line)
                if m:
                    value = m.group(1)
                    disc = int(value[0])
                    track = value[1:]
                    title = self.clean_track_name(m.group(2).strip())
                    merged.append((disc, track, title))
                    continue

            inorder = self._tracks_in_order(merged)
            if merged and len(merged) == n_files and inorder:
                self.log.info("Merged pattern produced valid results.")
                return {flac_files[i]: merged[i] for i in range(n_files)}
            else:
                msg = []
                if len(merged) != n_files:
                    msg.append(f"entries {len(merged)} != flacs {n_files}")
                if not inorder:
                    msg.append("tracks not in order")
                self.log.error(f"Parsing failed for {info_file}: {'; '.join(msg)}")

        # If we reach here, nothing matched
        return {}

    # -----------------------
    # Folder-level workflows
    # -----------------------
    def clear_title_tag_in_folder(self, directory_path: str) -> None:
        if not os.path.isdir(directory_path):
            print(f"Directory '{directory_path}' does not exist.")
            return

        for flac_file in glob(os.path.join(directory_path, "*.flac")):
            try:
                audio = FLAC(flac_file)
                if "title" in audio:
                    del audio["title"]
                    audio.save()
                    print(f"Cleared title tag from: {flac_file}")
                else:
                    print(f"No title tag found in: {flac_file}")
            except Exception as e:
                print(f"Error processing {flac_file}: {e}")

    def clear_song_specific_tags_in_folder(self, directory_path: str) -> None:
        if not os.path.isdir(directory_path):
            print(f"Directory '{directory_path}' does not exist.")
            return

        for flac_file in glob(os.path.join(directory_path, "*.flac")):
            try:
                audio = FLAC(flac_file)
                found_any = False
                for k in ("title", "tracknumber", "discnumber"):
                    if k in audio:
                        del audio[k]
                        print(f"Cleared {k} tag from: {flac_file}")
                        found_any = True
                if found_any:
                    audio.save()
                else:
                    print(f"No title/tracknumber/discnumber tags found in: {flac_file}")
            except Exception as e:
                print(f"Error processing {flac_file}: {e}")

    @staticmethod
    def add_line_numbers(file_path: str) -> None:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            logging.error(f"Error reading {file_path}: {e}")
            return

        new_lines: List[str] = []
        counter = 1
        for line in lines:
            if line.strip():
                new_lines.append(f"{counter:02d}. {line}")
                counter += 1
            else:
                new_lines.append(line)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            logging.info(f"Line numbers added to {file_path}")
        except Exception as e:
            logging.error(f"Error writing to {file_path}: {e}")

    # def tag_folder(self, directory: str, add_line_numbers_path: Optional[str] = None) -> bool:
    def tag_folder(self, directory: str, clear_song_tags: bool = False) -> bool:
        """
        Full workflow:
          - (optional) add line numbers to a given file
          - if all files already tagged, log & return
          - else parse the info file and tag
        Returns True iff all flacs are tagged at the end.
        """
        if not os.path.isdir(directory):
            self.log.error(f"{directory} is not a valid directory.")
            return False

        # if add_line_numbers_path:
        #     self.add_line_numbers(add_line_numbers_path)
        if clear_song_tags:
            self.clear_song_specific_tags_in_folder(directory)

        if not self.all_flac_tagged(directory):
            try:
                track_mapping = self.parse_info_file(directory)
            except ValueError as e:
                self.log.error(str(e))
                return False

            if track_mapping:
                self.tag_flac_files_wrapper(track_mapping)
            else:
                self.log.error(f"No Track Mapping for {directory}")
        else:
            self.log.info(f"Files are already tagged in {directory}")

        return self.all_flac_tagged(directory)

    def tag_folders(
        self, directories: List[str], clear_song_tags: bool = False
    ) -> None:
        """
        Tag multiple folders in sequence.
        """
        cleaned_folders = set()
        needfixing: List[str] = []

        for fldr in directories:
            cleaned_folders.add(Path(fldr).as_posix().strip())

        for directory in list(cleaned_folders):
            fld_status = self.tag_folder(directory, clear_song_tags=clear_song_tags)

            if fld_status:
                logging.info(f"All files tagged in {directory}")
            else:
                needfixing.append(directory)
                logging.error(f"No files tagged in {directory}")

        if needfixing:
            print("The following folders need investigation:")
            for x in needfixing:
                print(x)

        print(
            f"#Summary. Folders Processed Successfully: {len(folderlist) - len(needfixing)}  Untagged Folder Count: {len(needfixing)}"
        )


# -----------------------
# Main script usage

if __name__ == "__main__":
    tagger = FlacInfoFileTagger(
        log_to_file="flac_tagging.log", also_log_to_console=True
    )
    clear_song_tags = False

    folderlist = [
        r"X:\Downloads\_FTP\_Concerts_Unofficial\_renamed2\Phil\phil2005-05-15.90639"
    ]

    tagged_files = tagger.tag_folders(folderlist, clear_song_tags=clear_song_tags)
