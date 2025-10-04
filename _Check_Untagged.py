from InfoFileTagger import all_flac_tagged
from _Check_Unmatched import write_list_to_file
import os

from time import perf_counter

start_time = perf_counter()

untagged = []
for year in range(1970, 1992):
    parentfolder = rf"X:\Downloads\_FTP\gdead.{year}.project"
    concert_folders = sorted(
        [f.path.replace("\\", "/") for f in os.scandir(parentfolder) if f.is_dir()]
    )
    for fldr in concert_folders:
        try:
            if not all_flac_tagged(fldr):
                untagged.append(fldr)
        except Exception as e:
            print(f"Error in all_flac_tagged {e} {fldr}")
            raise Exception("E")

if untagged:
    print(f"{len(untagged)} untagged folders:")
    write_list_to_file(untagged, "untagged.txt")
    for fldr in untagged:
        print(fldr)
else:
    print("No untagged files")

end_time = perf_counter()
print(f"Runtime: {end_time - start_time:.4f} seconds")
