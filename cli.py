import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

from services.bootstrap import create_user_config, upgrade_user_config, user_config_path
from services.config import ConfigUpgradeRequired, LIBRARY_LOG_PATH, SHIPPED_CONFIG, load_app_config

from services.exceptions import FolderProcessingError, TaggerError
from tagger import ConcertTagger, SQLiteEtreeDB

logger = logging.getLogger(__name__)


def _discover_folders(parent: str, log_directory: Path | None = None) -> list[str]:
    parent_path = Path(parent)
    if not parent_path.is_dir():
        raise FileNotFoundError(f"Parent folder '{parent}' does not exist")
    return [
        child.path.replace('\\', '/')
        for child in os.scandir(parent_path)
        if child.is_dir()
        and Path(child.path).name.lower() != LIBRARY_LOG_PATH.parent.name
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
    try:
        concert_folders = gather_folders(args, Path(log_file).parent.resolve())
        for folder in concert_folders:
            if not Path(folder).is_dir():
                raise ValueError(f"Concert folder '{folder}' does not exist.")
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
