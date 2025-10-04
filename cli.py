import argparse
import logging
import os
from pathlib import Path
from time import perf_counter

from tagger import ConcertTagger, load_config, SQLiteEtreeDB


def _discover_folders(parent: str) -> list[str]:
    parent_path = Path(parent)
    if not parent_path.is_dir():
        raise FileNotFoundError(f"Parent folder '{parent}' does not exist")
    return [
        child.path.replace("\\", "/")
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
        default="tag_log.log",
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        filename=args.log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    start = perf_counter()

    config = load_config(args.config)
    etree_db = SQLiteEtreeDB(args.database)

    try:
        concert_folders = gather_folders(args)
        print(f"Processing tags for {len(concert_folders)} folders.")
        ConcertTagger.tag_shows(
            concert_folders,
            etree_db,
            config,
            clear_existing_tags=args.clear_tags,
        )
    finally:
        etree_db.close()

    elapsed = perf_counter() - start
    print(f"Runtime: {elapsed:.4f} seconds")
    logging.info("Runtime: %.4f seconds", elapsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#python cli.py --parent-folder "X:/Downloads/_FTP/_Tag_test" --clear-tags
