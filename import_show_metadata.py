
"""
Module: import_show_metadata
This module provides functionality to import show metadata from concert folders into an SQLite database
and then move processed folders to a designated destination. It checks for missing track titles, attempts
to tag files if necessary, updates the database with the extracted track metadata, and logs any errors or
mismatches encountered during processing.
Functions:
    import_show_folders(concert_folders: list, etree_db: SQLiteEtreeDB, config)
        Imports and processes a list of concert folders. For each folder, it checks if track titles exist,
        attempts to tag files when needed, updates the database with new metadata, and logs errors for any
        unprocessable folders.
        Parameters:
            concert_folders (list): List containing the paths of concert folders to be processed.
            etree_db (SQLiteEtreeDB): An instance representing the SQLite database connection.
            config: Configuration object used during the tagging process.
            tuple:
                successfully_imported (list): Folders that were successfully processed and imported.
                existing_folders (list): Folders which already contained matching track metadata.
    move_folder_if_not_exists(source_folder: str, destination_folder: str)
        Moves a folder from a source path to a specified destination if a folder with the same name does not
        already exist there. If the destination does not exist, it will try to create it before moving the folder.
        Parameters:
            source_folder (str): The path of the folder to be moved.
            destination_folder (str): The target directory where the folder should be moved.
            bool: True if the folder was successfully moved; False otherwise.
Main Execution:
    When executed as a script, the module configures logging, loads configurations from a file, sets up
    the SQLite database connection, processes the specified concert folders by importing show metadata,
    and then moves both newly imported and already existing show folders to a defined destination folder.
    The execution time is measured, and all significant actions and errors are logged.
"""
from time import perf_counter
from pathlib import Path
import os
import logging
from sqliteetreedb import SQLiteEtreeDB#, EtreeRecording
#from recordingfiles import RecordingFolder
from tagger import ConcertTagger
from tagger import load_config
import InfoFileTagger
import shutil

def import_show_folders(concert_folders:list, etree_db:SQLiteEtreeDB, config):
    """
    Import show folders into the database.
    This function processes each concert folder, checks for missing track titles,
    and attempts to tag the files if necessary. It logs any errors encountered
    during the process. If a folder is successfully tagged, it updates the database
    with the new track metadata.
    Args:
        concert_folders (list): List of concert folder paths to process.
        etree_db (SQLiteEtreeDB): Database connection object.
        config: Configuration object for the tagging process.
    Returns:
        successfully_imported (list): List of concert folders that were successfully imported to the database.
    """
    successfully_imported = []
    existing_folders = []
    try:
        with open("mismatched_folders.txt", "r", encoding="utf-8") as mismatchlogexisting:
            existing_mismatched_folders = mismatchlogexisting.readlines()
    except FileNotFoundError:
        existing_mismatched_folders = []
    with open("mismatched_folders.txt", "a", encoding="utf-8") as mismatchlog:
        for concert_folder in concert_folders:
            try:
                show = ConcertTagger(concert_folder,config,etree_db, debug=False)
                print(f'{show.etreerec.id=} {show.etreerec.md5key=} {show.folderpath=}')
                tracks = show.etreerec.tracks
                tracknames = [track.title for track in tracks]
                #print(f'{tracknames=}')
                if not tracknames:
                    tracks = [track.title for track in show.folder.musicfiles]
                    #for track in tracks:
                    #    print(f'{track}')
                    if None in tracks:
                        tagged = InfoFileTagger.tag_folder(show.folderpath)
                        if tagged:
                            print(f'Sucessfully tagged files in folder {concert_folder}')
                            show = ConcertTagger(concert_folder,config,etree_db)
                            tracks = [track.title for track in show.folder.musicfiles]
                        else:
                            error = f'Error tagging files in folder {concert_folder}'
                            print(error)
                            logging.error(error)
                            continue
                    
                    if None in tracks:
                        missingtitlefiles = ', '.join([file.name for file in show.folder.musicfiles if file.title is None])
                        error = f'Error Processing folder {concert_folder}: missing track title(s) {missingtitlefiles}'
                        print(error)
                        logging.error(error)
                    else:
                        rows = show.build_show_inserts()
                        print(f"inserting {len(rows)} rows for {concert_folder}")
                        show.db.insert_track_metadata(show.etreerec.id, rows,False,show.etreerec.md5key, debug = True)
                        successfully_imported.append(concert_folder)
                else:
                    existing_folders.append(concert_folder)
                    print(f"Matching tracknames exist for {concert_folder}")
            except Exception as e:
                logging.error(f'Error Processing folder {concert_folder} {e}')
                if concert_folder+'\n' not in existing_mismatched_folders:
                    mismatchlog.write(f"{concert_folder}\n")
    return successfully_imported, existing_folders

def move_folder_if_not_exists(source_folder: str, destination_folder: str):
    """
    Moves the source_folder into the festination_folder if it doesn't already exist there.
    If a folder with the same name already exists in the destination folder, the function
    prints and logs an error.

    Args:
        source_folder (str): The path of the folder to move.
        festination_folder (str): The destination folder where the source_folder will be moved.
    """
    # Determine the destination folder path by combining the festination_folder and the basename of source_folder.
    # Create destination folder if it doesn't exist.
    if not os.path.exists(destination_folder):
        try:
            os.makedirs(destination_folder)
            logging.info(f"Created destination folder '{destination_folder}'.")
        except Exception as e:
            error_message = f"Error creating destination folder '{destination_folder}': {e}"
            print(error_message)
            logging.error(error_message)
            return False    
    
    destination = os.path.join(destination_folder, os.path.basename(source_folder))
    
    # Check if the destination already exists.
    if os.path.exists(destination):
        error_message = f"Error: The folder '{destination}' already exists. Cannot move '{source_folder}'."
        print(error_message)
        logging.error(error_message)
        return False
    else:
        try:
            # Move the folder to the destination folder.
            shutil.move(source_folder, destination_folder)
            print(f"Successfully moved '{source_folder}' to '{destination_folder}'.")
            logging.info(f"Moved '{source_folder}' to '{destination_folder}'.")
            return True
        except Exception as e:
            error_message = f"Error moving '{source_folder}' to '{destination_folder}': {e}"
            print(error_message)
            logging.error(error_message)
            return False
        

if __name__ == "__main__":
    start_time = perf_counter()
    logfilename = 'tag_import.log' 
    logging.basicConfig(filename=logfilename,level=logging.WARN, format="%(asctime)s %(levelname)s: %(message)s")
    #TO DO: move more configuration to config.toml
    config_file = os.path.join(os.path.dirname(__file__),"config.toml")
    config = load_config(config_file)
    copy_success_path = r"X:\Downloads\_FTP\gdead.9999.updates_imported"
    sqlitepath_scrape = Path(r"E:\My Documents\GitHub\etree_tag\db\etree_scrape.db").as_posix()
    etreedb = SQLiteEtreeDB(sqlitepath_scrape)
    dirnm = r'X:\Downloads\_FTP\gdead.9999.updates'
    directorylist = [f.path.replace('\\','/') for f in os.scandir(dirnm) if f.is_dir()] 
    print(directorylist)
    imported_shows,existing_shows = import_show_folders(directorylist, etreedb, config)
    if imported_shows:
        print("Successfully imported the following shows:")
        for folder in imported_shows:
            print(f"moving {os.path.basename(folder)} to {copy_success_path}")
            move_folder_if_not_exists(folder, copy_success_path)
            

    if existing_shows:
        print("The following shows already exist in the database:")
        for folder in existing_shows:
            print(f"moving {os.path.basename(folder)} to {copy_success_path}")
            move_folder_if_not_exists(folder, copy_success_path)
            print(f"{folder}")
        
    etreedb.close
    end_time = perf_counter()
    print(f"Runtime: {end_time - start_time:.4f} seconds")
    logging.info(f"Runtime: {end_time - start_time:.4f} seconds")