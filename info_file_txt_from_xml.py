#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import os
import sys

def parse_archive_xml(xml_filename):


    #xml_filename = sys.argv[1]
    # Parse the XML file
    tree = ET.parse(xml_filename)
    root = tree.getroot()

    # Create output filename by replacing the extension with .txt
    base, _ = os.path.splitext(xml_filename)
    output_filename = base + ".txt"

    # Open output file for writing
    with open(output_filename, "w", encoding="utf-8") as out_file:
        # Loop through each <file> element in order
        for file_elem in root.findall("file"):
            if file_elem.get("source") == "original":
                track = file_elem.findtext("track", "").strip()
                title = file_elem.findtext("title", "").strip()
                if track and title:
                    out_file.write(f"{track} {title}\n")

    print(f"Output written to {output_filename}")

if __name__ == "__main__":
    filename = r"M:\To_Tag\gd1970\gd1970-05-24.6159.aud.hanno-uli.sbeok.flac16\gd1970-05-24.aud.6159.bunjes.shnf_files.xml"
    parse_archive_xml(filename)
