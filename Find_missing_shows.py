import logging
from sqliteetreedb import SQLiteEtreeDB
from tagger import ConcertTagger, load_config
from pathlib import Path
import os

def find_missing_shows(concert_folders:list, etree_db:SQLiteEtreeDB, config):
    with open("missing_shows2.txt", "a", encoding="utf-8") as file:
        for concert_folder in concert_folders:
            #print(f'{concert_folder}')
            try:
                tagger = ConcertTagger(concert_folder, config, etree_db)
                if not tagger.errormsg:
                    if not tagger.etreerec.tracks and tagger.etreerec.id:
                        print(f'no tracks found for folder{concert_folder} shnid = {tagger.etreerec.id}')
                        file.write(f"{concert_folder}\nshnid = {tagger.etreerec.id}\n")
                    if not tagger.etreerec.id:
                        logging.error(f'No match for {concert_folder}')
            except Exception as e:
                logging.error(f'Error Processing folder {concert_folder} {e}')
                print(f'Error Processing folder {concert_folder} {e}')
        #print(tagger.etreerec.tracks)

if __name__ == "__main__":
    from time import perf_counter
    start_time = perf_counter()
    logfilename = 'missingshows.log' 
    logging.basicConfig(filename=logfilename,level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    config_file = os.path.join(os.path.dirname(__file__),"config.toml")
    config = load_config(config_file)
    
    #concert_folders = [
    #    r"X:\Downloads\_FTP\gdead.1991.project\gd1991-05-12.31962.sbd.miller.sbeok.t-flac16"
    #]
    etreedb = SQLiteEtreeDB() #make sure this is outside the loop
    # for year in range(1971,1996):
    #     parentfolderpath = rf'X:\Music\Concerts\Concerts_GD\Grateful_Dead\gd{year}'
    #     parentfolder = Path(parentfolderpath).as_posix()
    #     concert_folders = sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()]) 
    #     find_missing_shows(concert_folders,etreedb,config)

    #     parentfolderpath = rf'M:\ConvertSHN\Grateful_Dead\gd{year}'
    #     parentfolder = Path(parentfolderpath).as_posix()
    #     concert_folders = sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()]) 
    #     find_missing_shows(concert_folders,etreedb,config)
    
    #concert_folders= [r'M:\To_Tag\gd1979\gd1979-xx-xx.gthroughmixes.samaritano.xxxxx.flac16']
    #find_missing_shows(concert_folders,etreedb,config)

    parentfolderpath = r'X:\Downloads\_FTP\HuntersTrix'
    parentfolder = Path(parentfolderpath).as_posix()
    concert_folders = sorted([f.path.replace('\\','/') for f in os.scandir(parentfolder) if f.is_dir()]) 
    find_missing_shows(concert_folders,etreedb,config)    


    etreedb.close
    
    end_time = perf_counter()
    print(f"Runtime: {end_time - start_time:.4f} seconds")
    logging.info(f"Runtime: {end_time - start_time:.4f} seconds")
    
        
                    



    # Example: For a concert on 1975-03-23 by Bob Dylan (artist abbreviation "gd")
    #artwork = tagger._find_artwork("gd", etreerec.date)
    #if artwork:
    ##    print(f"Found artwork: {artwork}")
    #else:
    #    print("No artwork found.")
