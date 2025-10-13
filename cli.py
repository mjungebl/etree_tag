import argparse
import logging
import os
from pathlib import Path
from time import perf_counter

from services.exceptions import (
    ConfigurationError,
    FolderProcessingError,
    TaggerError,
)
from tagger import ConcertTagger, SQLiteEtreeDB, load_config

logger = logging.getLogger(__name__)


def _discover_folders(parent: str) -> list[str]:
    parent_path = Path(parent)
    if not parent_path.is_dir():
        raise FileNotFoundError(f"Parent folder '{parent}' does not exist")
    return [
        child.path.replace('\\', '/')
        for child in os.scandir(parent_path)
        if child.is_dir()
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
        default=os.path.join(os.path.dirname(__file__), "config.toml"),
        help="Path to config TOML file (default: %(default)s)",
    )
    parser.add_argument(
        "--database",
        default="db/etree_scrape.db",
        help="Path to SQLite database (default: %(default)s)",
    )
    parser.add_argument(
        "--clear-tags",
        action="store_true",
        help="Clear existing FLAC tags before writing new metadata.",
    )
    parser.add_argument(
        "--log-file",
        default="log/tag_log.log",
        help="Log file to write progress information (default: %(default)s)",
    )
    return parser.parse_args(argv)



def gather_folders(args: argparse.Namespace) -> list[str]:
    folders = list(args.folders)
    if args.parent_folder:
        folders.extend(_discover_folders(args.parent_folder))
    if not folders:
        raise ValueError("No concert folders specified. Provide paths or --parent-folder.")
    return sorted({Path(folder).as_posix() for folder in folders})



def _configure_logging(log_file: str) -> logging.Logger:
    """Configure global logging handlers for console and file output."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger.addHandler(console_handler)

    return console_handler



def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    console_handler = _configure_logging(args.log_file)

    start = perf_counter()

    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        logger.error(str(exc))
        return 1

    if getattr(config.preferences, "verbose_logging", False):
        logging.getLogger().setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled via configuration.")

    etree_db = SQLiteEtreeDB(args.database)

    try:
        concert_folders = gather_folders(args)
    except ValueError as exc:
        logger.error(str(exc))
        etree_db.close()
        return 1

    logger.debug("Processing tags for %d folders.", len(concert_folders))

    try:
        ConcertTagger.tag_shows(
            concert_folders,
            etree_db,
            config,
            clear_existing_tags=args.clear_tags,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#python cli.py --parent-folder "X:/Downloads/_FTP/_Tag_test" --clear-tags
