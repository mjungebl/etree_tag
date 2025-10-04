# from pathlib import Path
# import os
# folders = read_file_to_list(r'logs/unmatched.txt')
# if folders:
#    move_folders_concurrently(folders,Path(r'X:/Downloads/_FTP/_unmatched').as_posix(),4)
from tagger import ConcertTagger, load_config
from sqliteetreedb import SQLiteEtreeDB
import os
from pathlib import Path

if __name__ == "__main__":
    config_file = os.path.join(os.path.dirname(__file__), "config.toml")
    config = load_config(config_file)
    sqlitepath_scrape = Path(
        r"E:\My Documents\GitHub\etree_tag\db\etree_scrape.db"
    ).as_posix()
    etreedb = SQLiteEtreeDB(sqlitepath_scrape)
    unmatched = []
    parentofparents = r"X:\Downloads\Further"
    # parentfolder = r'X:\Downloads\Further\2010'
    for parentfolder in sorted(
        [f.path.replace("\\", "/") for f in os.scandir(parentofparents) if f.is_dir()]
    ):
        # for parentfolder in [r'X:\Downloads\_FTP\gdead.9999.updates']:
        # folder = r'X:\Downloads\Further\2009\2009-09-20 Fox Theater, Oakland, CA'
        if "_fail" in parentfolder:
            continue
        if "_mismatches" in parentfolder:
            continue
        if "_foundMatches" in parentfolder:
            continue
        # if 'LL' not in parentfolder:
        #   continue
        for folder in sorted(
            [f.path.replace("\\", "/") for f in os.scandir(parentfolder) if f.is_dir()]
        ):
            # if folder.startswith('_'):
            #    continue
            tagger = ConcertTagger(folder, config, etreedb)
            if tagger.etreerec:
                print(tagger.etreerec.id)
            else:
                unmatched.append(folder)

    if unmatched:
        print(f"The following {len(unmatched)} items to not match an existing shnid:")
        for folder in unmatched:
            print(folder)
        # move_folders_concurrently(unmatched,Path(r'X:\Downloads\Further\_mismatches').as_posix(),4)
# from _Check_Unmatched import move_folders_concurrently, read_file_to_list
# from pathlib import Path
# import os
# folders = read_file_to_list(r'logs/unmatched.txt')
# if folders:
#
