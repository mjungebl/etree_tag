from sqliteetreedb import SQLiteEtreeDB
from tagger import ConcertTagger, load_config
from pathlib import Path
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

def write_list_to_file(lst, file_name):
    """
    Writes each element of the list 'lst' to a file specified by 'file_name'.
    If the file exists, appends the data; otherwise, creates a new file.
    Assumes that 'file_name' is a relative path unless it is an absolute path.

    :param lst: List of items to write to the file.
    :param file_name: Name of the file (relative or absolute path).
    """
    # If file_name is not absolute, treat it as relative to the current working directory.
    if not os.path.isabs(file_name):
        file_path = os.path.join(os.getcwd(), file_name)
    else:
        file_path = file_name

    # Open file in append mode. Each list item is written on a new line.
    with open(file_path, "a", encoding="utf-8") as f:
        for item in lst:
            f.write(str(item) + "\n")


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


def move_folder(folder, destination_dir):
    """
    Moves a single folder to the destination directory.
    Returns the folder and its new destination path.
    """
    if not os.path.isdir(folder):
        raise ValueError(f"Source path '{folder}' is not a valid directory.")

    folder_name = os.path.basename(os.path.normpath(folder))
    dest_path = os.path.join(destination_dir, folder_name)
    shutil.move(folder, dest_path)
    return folder, dest_path


def move_folders_concurrently(folder_paths, destination_dir, max_workers=4):
    """
    Moves multiple folders concurrently to a specified destination directory.

    Parameters:
        folder_paths (list of str): List of folder paths to move.
        destination_dir (str): The target directory.
        max_workers (int): Maximum number of worker threads.

    Returns:
        None
    """
    if not os.path.exists(destination_dir):
        os.makedirs(destination_dir)
        print(f"Created destination directory: {destination_dir}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_folder = {
            executor.submit(move_folder, folder, destination_dir): folder
            for folder in folder_paths
            if os.path.isdir(folder)
        }
        for future in as_completed(future_to_folder):
            folder = future_to_folder[future]
            try:
                src, dest = future.result()
                print(f"Moved '{src}' to '{dest}'")
            except Exception as e:
                print(f"Error moving '{folder}': {e}")


# Example usage:
# folder_list = ['/path/to/folder1', '/path/to/folder2', '/path/to/folder3']
# move_folders_concurrently(folder_list, '/destination/path', max_workers=8)


##############################################################################################


# Assume these are defined elsewhere:
# concert_folders: a list of folder paths to process.
# config: configuration details needed by ConcertTagger.
# ConcertTagger: a class that accepts (folder, config, db_connection).

# nomatch = []
nomatch_lock = Lock()


def process_folder(folder):
    print(folder)
    # Create a separate SQLite connection for this thread.
    # Replace 'path_to_your_db.db' with your actual database file.
    local_db = SQLiteEtreeDB()

    # Initialize ConcertTagger with the thread-local database connection.
    tg = ConcertTagger(folder, config, local_db)
    if tg.NoMatch:
        # Process the folder.
        #    if not tg.etreerec and tg.folder.musicfiles:
        with nomatch_lock:
            nomatch.append(folder)

    # Always close the connection after processing.
    local_db.close()


# # Use ThreadPoolExecutor to run the tasks concurrently.
# with ThreadPoolExecutor(max_workers=8) as executor:
#     futures = [executor.submit(process_folder, folder) for folder in concert_folders]
#     for future in as_completed(futures):
#         # Propagate any exception raised in a thread.
#         future.result()

# There is no global SQLite connection to close in the main thread.
# print("Folders with no match:", nomatch)

##########################################################################################################################
if __name__ == "__main__":
    from time import perf_counter

    start_time = perf_counter()
    nomatch = []
    sqllite_path = r"E:\My Documents\GitHub\etree_tag\db\etree_scrape.db"
    etreedb = SQLiteEtreeDB(sqllite_path)
    config_file = os.path.join(os.path.dirname(__file__), "config.toml")
    config = load_config(config_file)
    # etreedb.vacuum_database()
    # tables = etreedb.get_table_sizes()
    # parentfolderpath = r'Z:\Music\Grateful Dead\gd1991'
    for year in range(2009, 2015):
        # for year in range(0,1):
        # parentfolderpath = rf'X:\Downloads\_FTP\gdead.{year}.project'
        parentfolderpath = rf"X:\Downloads\Further\{year}"
        # parentfolderpath = r'X:\Downloads\_FTP\gdead.1989.project'
        parentfolder = Path(parentfolderpath).as_posix()
        concert_folders = sorted(
            [f.path.replace("\\", "/") for f in os.scandir(parentfolder) if f.is_dir()]
        )
        # concert_folders = [r'X:/Downloads/_FTP/gdead.1987.project/gd1987-07-19.97651.013023+097651.sbd.combined.t-flac16',]
        ##############################################
        # for folder in concert_folders:
        #     print(folder)
        #     tg = ConcertTagger(folder,config,etreedb)
        #     if not tg.etreerec and tg.folder.musicfiles:
        #         nomatch.append(folder)
        #################################################

        # Use ThreadPoolExecutor to run the tasks concurrently.
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(
                    process_folder,
                    folder,
                )
                for folder in concert_folders
            ]
            for future in as_completed(futures):
                # Propagate any exception raised in a thread.
                future.result()
    # print(tables)
    etreedb.close()

    if nomatch:
        write_list_to_file(nomatch, "logs/unmatched.txt")
        print(
            f"The folowing ({len(nomatch)}) folders did not match to an entry in the database:"
        )
        for folder in nomatch:
            print(folder)
    else:
        print("Everything had a match.")

    end_time = perf_counter()
    print(f"Runtime: {end_time - start_time:.4f} seconds")
