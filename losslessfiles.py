import os
import subprocess
from pathlib import Path
from filefolder_org import remove_empty_file, load_config
from mutagen.flac import FLAC
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

config_file = os.path.join(os.path.dirname(__file__), "config.toml")
config = load_config(config_file)
PathToFlac = config.supportfiles.get("flac")
PathToMetaflac = config.supportfiles.get("metaflac")

# print(f'{PathToFlac=} {PathToMetaflac=}')






class ffp:
    """class to hold a ffp file, which contains the checksums for all flac files in a directory"""

    def __init__(
        self,
        location: str,
        name: str,
        signatures: dict = {},
        metaflacpath: str = None,
        flacpath: str = None,
    ):
        """
        Initialize the ffp object with the location and name of the ffp file, and optionally the metaflac and flac paths.
        If metaflacpath or flacpath is not provided, it will use the default paths from the config file.
        :param location: The directory where the ffp file is located.
        :param name: The name of the ffp file.
        :param signatures: A dictionary of file paths and their corresponding checksums.
        :param metaflacpath: The path to the metaflac executable. If None, it will use the default path from the config file.
        :param flacpath: The path to the flac executable. If None, it will use the default path from the config file.
        """
        self.location = location
        self.name = name
        # if metaflacpath is not None:
        self.metaflacpath = metaflacpath if metaflacpath is not None else PathToMetaflac
        self.flacpath = flacpath if flacpath is not None else PathToFlac
        self.signatures = signatures
        self.errors = []
        self.result = []

    def readffpfile(self):
        """split ffp file into dictionary with full file path as key and signature as value"""
        ffp_path = Path(self.location) / self.name
        try:
            try:
                content = ffp_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = ffp_path.read_text()
        except Exception as e:
            msg = f"Error reading file {ffp_path}: {e}"
            print(msg)
            self.errors.append(msg)
            return

        try:
            entries = parse_flac_fingerprint(content)
            ffp_sigs = {
                filename.replace("\\", "/"): checksum for filename, checksum in entries
            }
            self.signatures = ffp_sigs
        except Exception as e:  # pragma: no cover - defensive, shouldn't occur
            msg = f"Error parsing file {ffp_path}: {e}"
            self.errors.append(msg)

    def generate_checksums(self):
        """loop though all files and child directories to generate the checksums for all .flac files, storing them with the relative path"""
        DirectoryName = self.location + "/"
        b_error = False
        self.signatures = {}
        for path, directories, files in os.walk(DirectoryName):
            for file in files:
                if file.lower().endswith(".flac"):
                    filepath = Path(path.replace("\\", "/") + "/" + file).as_posix()
                    try:
                        if len(filepath) > 260:
                            raise Exception(f"Path too long: {filepath =}")
                    except Exception as e:
                        b_error = True
                        Err = f"Error: {e}"  # sys.error(e)
                        self.errors.append(Err)
                    if not b_error:
                        try:
                            # fingerprint = subprocess.check_output('"'+self.metaflacpath+'"'+' --show-md5sum "'+filepath+'"', encoding="utf8")
                            # with open(filepath, 'rb') as f:
                            flac_file = FLAC(
                                filepath
                            )  # using mutagen prevents the need to call the metaflac cmd.
                            fingerprint = ("%02x" % flac_file.info.md5_signature).rjust(
                                32, "0"
                            )

                            if (
                                fingerprint.strip()
                                == "00000000000000000000000000000000"
                            ):
                                b_error = True
                                Err = f"Error in file: {filepath}. Fingerprint = {fingerprint.strip()}"
                                self.errors.append(Err)
                                print(Err)
                            else:
                                self.signatures[filepath.replace(DirectoryName, "")] = (
                                    fingerprint.strip()
                                )
                        except Exception as e:
                            Err = f"Error: {e}"
                            self.errors.append(Err)
                            print(Err)
                            b_error = True
        if b_error:
            print("Error Generating checksums for: " + DirectoryName)
            # return ([],None)
        else:
            if len(self.signatures) == 0:
                print("No checksums generated for: " + DirectoryName)
                # return ([],None)
            else:
                print("Checksums generated for: " + DirectoryName)

    def SaveFfp(self):
        """This function will create a ffp file in the specified directory using the values passed in"""
        FileName = self.location + "/" + self.name
        if self.signatures:
            try:
                # output_file = open(FileName, 'w', encoding="utf-8")
                with open(FileName, "w", encoding="utf-8") as output_file:
                    # for key,value in self.signatures.items():
                    for key in sorted(self.signatures):
                        value = self.signatures[key]
                        output_file.write(key + ":" + value + "\n")
                    # output_file.close()
                print(f"Created file: {FileName}")
            except Exception as e:
                # errors may occur occasionally when there is a bad character in a flac filename. Do not create the ffp file if an exception occurs
                # if output_file.closed == False:
                #    output_file.close()
                remove_empty_file(FileName)
                print(f"ERROR Creating file: {e}")
        else:
            print(f"No signatures file not created: {FileName}")

    def verify(self, silent=False):
        # return None
        """verify an ffp file"""
        self.result = []
        self.errors = []
        print(f"Verifying {self.name} in {self.location}:")
        # a single process is not maxing out the disk when verifying, speed things up a bit...
        # with concurrent.futures.ProcessPoolExecutor() as executor:
        # multithreading appears to be a bit faster
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    verifyflacfile,
                    filenm,
                    checksum,
                    self.flacpath,
                    self.metaflacpath,
                    self.name,
                    self.location,
                ): (filenm, checksum)
                for (filenm, checksum) in list(self.signatures.items())
            }
            for future in concurrent.futures.as_completed(futures):
                Err = None
                message = None
                Err, message = future.result()
                if Err is None:
                    # print(message)
                    # logger.info(message)
                    self.result.append(message)
                else:
                    self.errors.append(Err)
                    # logger.error(Err)
                if not silent:
                    print("\t" + message if Err is None else Err)


def verifyflacfile(filenm, checksum, fp, mfp, ffpnm, loc):
    """check an individual flac file"""
    filepath = loc + "/" + filenm
    Error = None
    try:
        # fingerprint = subprocess.check_output('"'+mfp+'"'+' --show-md5sum "'+loc+'/'+filenm+'"', encoding="utf8")
        flac_file = FLAC(
            filepath
        )  # using mutagen prevents the need to call the metaflac cmd.
        fingerprint = ("%02x" % flac_file.info.md5_signature).rjust(32, "0")
        if fingerprint.strip() == "00000000000000000000000000000000":
            Error = msg = (
                f"Error in file: {filenm}. Path: {filenm} cannot check MD5 signature since it was unset in the STREAMINFO"
            )
    # except  subprocess.CalledProcessError as e:
    except Exception as e:
        # logger.error(e.cmd)
        Error = msg = f"Error: {e}"
    try:
        # rawfingerprint = calcflacfingerprint(filepath)
        # if rawfingerprint != fingerprint:
        #    msg = f"{filenm}:{rawfingerprint} does not match {checksum}."
        subprocess.check_output(
            '"' + fp + '"' + ' --test --silent "' + loc + "/" + filenm, encoding="utf8"
        )
        if str(checksum).strip() == fingerprint.strip():
            msg = f"{filenm}:{checksum} passed."
        else:
            Error = msg = (
                f"Error in file: {ffpnm}. Path: {filenm}:{checksum} verified, but does not match signature."
            )
    except Exception as e:
        Error = msg = f"Error verifying file: {filenm}:\n\t {e}"
    # print('\t'+msg if Error == None else Err)
    return Error, msg






class albumfolder:
    """class to hold a directory containing flac files, equivalent to an album or a concert. in some cases the flac files may be located in sub directories divided by discs"""

    def __init__(self, location: str):
        self.location = location


class artistfolder:
    def __init__(self, location: str):
        self.location = location


class md5:
    def __init__(self, location: str, name: str, signatures: dict):
        self.location = location
        self.name = name
        # if signatures == {}:
        #    self.readffpfile()
        # else:
        self.signatures = signatures
        self.errors = []
        self.result = []

    def readmd5file(self):
        """split md5 file into dictionary with full file path as key and signature as value"""
        md5_path = Path(self.location) / self.name
        try:
            try:
                content = md5_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = md5_path.read_text()
        except Exception as e:
            msg = f"Error reading file {md5_path}: {e}"
            print(msg)
            self.errors.append(msg)
            return

        try:
            entries = parse_md5(content)
            md5_sigs = {
                filename.replace("\\", "/"): checksum for filename, checksum in entries
            }
            self.signatures = md5_sigs
        except Exception as e:  # pragma: no cover - defensive
            msg = f"Error parsing file {md5_path}: {e}"
            self.errors.append(msg)








def parse_flac_fingerprint(filecontent: str) -> list[tuple[str, str]]:
    """
    Parse lines in FFP format and return a list of records,
    each as ``(audio_filename, audio_checksum)``.
    """
    lines = filecontent.splitlines()
    records: list[tuple[str, str]] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if ":" in line:
            audio_filename, audio_checksum = line.rsplit(":", 1)
            records.append((audio_filename.strip(), audio_checksum.strip()))
        else:
            print(f"Unexpected flac fingerprint line format: {line}")
    return records


def parse_st5(filecontent: str) -> list[tuple[str, str]]:
    """
    Parse ST5 content and return a list of entries in the format
    ``(audio_filename, audio_checksum)``.
    """
    lines = filecontent.splitlines()
    records: list[tuple[str, str]] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if " " in line:
            checksum, filename = line.split(maxsplit=1)
            records.append((filename.strip(), checksum.strip()))
        else:
            print(f"Unexpected st5 line format: {line}")

    return records


def parse_md5(filecontent: str) -> list[tuple[str, str]]:
    """
    Parse traditional MD5 checksum files with lines like: ``checksum *filename``.
    """
    lines = filecontent.splitlines()
    records: list[tuple[str, str]] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if " " in line:
            checksum, filename = line.split(maxsplit=1)
            records.append((filename.strip("* ").strip(), checksum.strip()))
        else:
            print(f"Unexpected md5 line format: {line}")
    return records
