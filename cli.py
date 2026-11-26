import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from functools import cache
from pathlib import Path
from time import perf_counter

from recordingfiles import RecordingFolder
from services.bootstrap import create_user_config, save_flac_path, upgrade_user_config, user_config_path
from services.config import ConfigUpgradeRequired, LIBRARY_LOG_PATH, SHIPPED_CONFIG, load_app_config

from services.exceptions import FolderProcessingError, TaggerError
from services.shn_conversion import SOURCE_ARCHIVE, convert_shn, describe_conversion
from services.verification import choose_flac, verify_show, verify_show_with_receipt
from tagger import ConcertTagger, SQLiteEtreeDB

logger = logging.getLogger(__name__)


def _show_progress(folder):
    def report(message):
        print(f"{folder.name}: {message}", flush=True)

    return report


def _discover_folders(parent: str, log_directory: Path | None = None) -> list[str]:
    parent_path = Path(parent)
    if not parent_path.is_dir():
        raise FileNotFoundError(f"Parent folder '{parent}' does not exist")
    return [
        child.path.replace('\\', '/')
        for child in os.scandir(parent_path)
        if child.is_dir()
        and Path(child.path).name.lower() not in {LIBRARY_LOG_PATH.parent.name, SOURCE_ARCHIVE}
        and Path(child.path).resolve() != log_directory
    ]



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tag FLAC shows with metadata and artwork.")
    parser.add_argument(
        "folders",
        nargs="*",
        help="Explicit concert folders to tag.",
    )
    parser.add_argument(
        "--parent-folder",
        dest="parent_folder",
        help="Process all subdirectories contained in the specified parent folder.",
    )
    parser.add_argument(
        "--config",
        help="Use an explicit TOML instead of the saved user configuration.",
    )
    parser.add_argument(
        "--database",
        help="Override the saved SQLite database path.",
    )
    parser.add_argument(
        "--clear-tags",
        action=argparse.BooleanOptionalAction,
        help="Override whether existing FLAC tags are cleared.",
    )
    parser.add_argument(
        "--log-file",
        help="Override the base log file path. Each run prefixes the filename with a timestamp.",
    )
    parser.add_argument(
        "--verify", action=argparse.BooleanOptionalAction,
        help="Check FLAC audio and available SHN MD5 manifests before tagging.",
    )
    parser.add_argument("--flac", help="Path to the FLAC executable for this run.")
    parser.add_argument(
        "--reuse-verification", action=argparse.BooleanOptionalAction,
        help="Verify shows using saved receipts when their audio and checksums are unchanged.",
    )
    parser.add_argument(
        "--convert-shn", action=argparse.BooleanOptionalAction,
        help="Convert SHN-only sets before the tagging preview using the saved conversion options.",
    )
    parser.add_argument("--ffmpeg", help="Path to FFmpeg for --convert-shn (defaults to PATH).")
    return parser.parse_args(argv)



def gather_folders(args: argparse.Namespace, log_directory: Path | None = None) -> list[str]:
    folders = list(args.folders)
    if args.parent_folder:
        folders.extend(_discover_folders(args.parent_folder, log_directory))
    if not folders:
        raise ValueError("No concert folders specified. Provide paths or --parent-folder.")
    return sorted({Path(folder).as_posix() for folder in folders})



def _configure_logging(log_file: str, verbose: bool) -> None:
    """Configure global logging handlers for console and file output."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    level = logging.DEBUG if verbose else logging.INFO
    root_logger.setLevel(level)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.addFilter(lambda record: record.name == logger.name)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger.addHandler(console_handler)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    start = perf_counter()
    managed_config = args.config is None
    path = user_config_path() if managed_config else Path(args.config).expanduser()
    default_database = "db/etree_scrape.db"
    default_log = "log/tag_log.log"
    try:
        if managed_config and not path.exists():
            if not sys.stdin.isatty():
                print(
                    f"No user settings at {path}. Run python cli.py in an interactive "
                    "terminal to set up Etree Tag, or pass --config with an existing TOML.",
                    file=sys.stderr,
                )
                return 1
            create_user_config(
                path,
                args.database or str(SHIPPED_CONFIG.parent / default_database),
                args.log_file,
            )
            return 0
        try:
            config = load_app_config(path, user_config=managed_config)
        except ConfigUpgradeRequired as exc:
            if not sys.stdin.isatty():
                print(
                    f"{exc} File: {path}. "
                    "Run the same command in an interactive terminal.",
                    file=sys.stderr,
                )
                return 1
            upgrade_user_config(path)
            return 0
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Configuration error ({path}): {exc}", file=sys.stderr)
        return 1

    if not args.parent_folder and not args.folders and config.run.library_folder:
        if config.run.scan_subfolders:
            args.parent_folder = config.run.library_folder
        else:
            args.folders = [config.run.library_folder]
    database = args.database or config.run.database or default_database
    library = config.run.library_folder or args.parent_folder
    if not library and len(args.folders) == 1:
        library = args.folders[0]
    log_base = Path(args.log_file or config.run.log_file or (
        str(Path(library) / LIBRARY_LOG_PATH) if library else default_log
    ))
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    log_file = log_base.with_name(f"{timestamp}_{log_base.name}")
    clear_tags = config.run.clear_tags if args.clear_tags is None else args.clear_tags
    verify = (config.run.verify or args.reuse_verification is True) if args.verify is None else args.verify
    reuse_verification = (
        config.run.reuse_verification if args.reuse_verification is None else args.reuse_verification
    )
    verification_options = {}
    try:
        concert_folders = gather_folders(args, Path(log_file).parent.resolve())
        for folder in concert_folders:
            if not Path(folder).is_dir():
                raise ValueError(f"Concert folder '{folder}' does not exist.")
        has_shn_only = any(
            not any(Path(folder).glob("*.flac")) and any(Path(folder).glob("*.shn"))
            for folder in concert_folders
        )
        shn_settings = config.shn_conversion
        convert = has_shn_only and (shn_settings.enabled if args.convert_shn is None else args.convert_shn)
        if convert:
            ffmpeg_path = args.ffmpeg or config.supportfiles.get("ffmpeg") or "ffmpeg"
            ffmpeg = shutil.which(str(Path(ffmpeg_path).expanduser()))
            if not ffmpeg:
                raise ValueError("SHN conversion needs FFmpeg. Add it to PATH or pass --ffmpeg PATH.")
        if verify or convert:
            @cache
            def get_flac():
                configured_flac = args.flac or config.supportfiles.files.get("flac")
                if configured_flac and not args.flac:
                    configured_flac = str(path.parent / Path(configured_flac).expanduser())
                return choose_flac(
                    configured_flac,
                    interactive=sys.stdin.isatty(),
                    remember=(lambda executable: save_flac_path(path, executable)) if managed_config else None,
                )

            flac = None
            if convert or (not reuse_verification and any(
                any(Path(folder).glob("*.flac")) for folder in concert_folders
            )):
                flac = get_flac()
                if flac is None:
                    return 1
            if verify and reuse_verification:
                verification_options["verify_folder"] = lambda folder: verify_show_with_receipt(
                    folder, get_flac, progress=_show_progress(folder),
                )
            elif verify:
                verification_options["verify_folder"] = lambda folder: verify_show(
                    folder, flac, progress=_show_progress(folder),
                )
            if convert:
                verification_options["describe_conversion"] = lambda folder: describe_conversion(
                    folder, RecordingFolder._parse_shnid(folder.name),
                    shn_settings.compression_level, shn_settings.paranoid,
                )
                verification_options["convert_folder"] = lambda folder, conversion_manifest: convert_shn(
                    folder, ffmpeg, flac, RecordingFolder._parse_shnid(folder.name),
                    compression_level=shn_settings.compression_level,
                    paranoid=shn_settings.paranoid,
                    generated_files=(log_file.resolve(), conversion_manifest.resolve()),
                    progress=_show_progress(folder),
                )
        if not Path(database).parent.is_dir() or Path(database).is_dir():
            raise ValueError(f"Invalid SQLite database path '{database}'.")
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        _configure_logging(str(log_file), config.preferences.verbose_logging)
    except (OSError, ValueError) as exc:
        print(f"Could not start tagging: {exc}", file=sys.stderr)
        return 1

    try:
        etree_db = SQLiteEtreeDB(database)
    except Exception:
        logger.exception("Could not open SQLite catalog %s", database)
        return 1

    logger.debug("Processing tags for %d folders.", len(concert_folders))

    try:
        completed = ConcertTagger.tag_shows(
            concert_folders,
            etree_db,
            config,
            clear_existing_tags=clear_tags,
            manifest_path=log_file.with_name(f"{timestamp}_changes.txt"),
            **verification_options,
        )
    except FolderProcessingError as exc:
        logger.error(str(exc))
        return 1
    except TaggerError as exc:
        logger.error("Tagging failed: %s", exc)
        return 1
    except Exception:
        logger.exception("Unexpected error while tagging shows.")
        return 1
    finally:
        etree_db.close()

    elapsed = perf_counter() - start
    logger.info("Runtime: %.4f seconds", elapsed)
    return 1 if completed is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
#python cli.py --parent-folder "X:/Downloads/_FTP/_Tag_test" --clear-tags
