"""Plan and review recording edits before writing them."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace

from mutagen.flac import FLAC

from services.exceptions import MetadataImportError
from services.tagging import prepare_file_tags

logger = logging.getLogger(__name__)
COVER_EXTENSIONS = ("jpg", "jpeg", "png", "gif", "bmp", "webp")


def file_state(path):
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return None
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@dataclass
class ArtworkPlan:
    source: Path | None = None
    destination: Path | None = None
    image: bytes | None = None
    replace: bool = False
    backups: dict[Path, Path] = field(default_factory=dict)
    removals: list[Path] = field(default_factory=list)
    expected: dict = field(default_factory=dict)

    @classmethod
    def build(cls, folder, source, clear, retain):
        if not source:
            return cls()
        paths = [folder / f"folder.{ext}" for ext in COVER_EXTENSIONS]
        expected = {path: file_state(path) for path in paths}
        existing = [path for path in paths if path.exists()]
        source = existing[0] if existing and not clear else Path(source)
        destination = existing[0] if existing else folder / f"folder{source.suffix.lower()}"
        expected[destination] = file_state(destination)
        image = source.read_bytes()
        plan = cls(source, destination, image, expected=expected)
        if existing and destination.read_bytes() == image:
            return plan
        plan.replace = True
        for path in existing:
            backup = path.with_name(f"{path.name}.old")
            if retain and file_state(backup) is None:
                plan.backups[path] = backup
                expected[backup] = None
            elif path != destination:
                plan.removals.append(path)
        return plan

    def describe(self):
        if self.replace:
            yield f"  Write {self.destination.name} from {self.source}"
        for path, backup in self.backups.items():
            yield f"  Back up {path.name} as {backup.name}"
        for path in self.removals:
            yield f"  Remove {path.name}"

    def apply(self):
        if not self.replace:
            return
        temporary = None
        try:
            with NamedTemporaryFile(dir=self.destination.parent, delete=False) as staged:
                temporary = Path(staged.name)
                staged.write(self.image)
            for path, backup in self.backups.items():
                path.rename(backup)
            for path in self.removals:
                path.unlink()
            temporary.replace(self.destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _local_tracks(tagger, loaded):
    """Project local track metadata without writing intermediary FLAC tags."""
    importer = tagger.metadata_importer
    info = importer.info_tagger
    directory = str(tagger.folderpath)

    def project(mapping, *, overwrite=False):
        records = []
        for file, audio in loaded:
            disc = next(iter(audio.get("discnumber", [])), None)
            track = next(iter(audio.get("tracknumber", [])), None)
            title = next(iter(audio.get("title", [])), None)
            proposed = mapping.get(str(Path(file.path).resolve()))
            if proposed:
                new_disc, new_track, new_title = proposed
                if overwrite or not (disc and track) or (disc, track) == (str(new_disc), new_track):
                    disc = str(new_disc) if overwrite else disc or str(new_disc)
                    track = new_track if overwrite else track or new_track
                    title = new_title
            if not (track and track.strip() and title and title.strip()):
                return []
            records.append((
                tagger.etreerec.id, disc, track, title.strip(), file.checksum,
                audio.info.bits_per_sample, audio.info.sample_rate, file.length,
                audio.info.channels, file.name,
            ))
        return records

    records = project({})
    if not records:
        try:
            mapping = info.parse_info_file(directory)
        except ValueError:
            mapping = {}
        records = project({str(Path(path).resolve()): value for path, value in mapping.items()})
    if not records and importer.enable_filename_fallback:
        mapping = importer._derive_mapping_from_filenames(tagger)
        records = project(
            {str(Path(path).resolve()): value for path, value in mapping.items()},
            overwrite=True,
        )
    if not records:
        raise MetadataImportError(f"Could not derive complete track metadata for {directory}")
    tracks = {}
    for _, disc, track, title, checksum, *_ in records:
        clean, segue = tagger.db.clean_title_field(title)
        tracks.setdefault(checksum, SimpleNamespace(disc=disc, tracknum=track, title=clean, gazinta=segue))
    return tracks, records


def _tags(audio):
    return {key: list(audio[key]) for key in audio.keys()}


def _rename_show(folder, destination):
    """Release log handles within the show while Windows renames it."""
    root = logging.getLogger()
    handlers = [
        handler for handler in root.handlers
        if isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).is_relative_to(folder)
    ]
    for handler in handlers:
        root.removeHandler(handler)
        handler.close()
    log_folder = folder
    try:
        folder.rename(destination)
        log_folder = destination
    finally:
        for handler in handlers:
            path = log_folder / Path(handler.baseFilename).relative_to(folder)
            replacement = logging.FileHandler(path, encoding=handler.encoding)
            replacement.setLevel(handler.level)
            replacement.setFormatter(handler.formatter)
            root.addHandler(replacement)


@dataclass
class ShowPlan:
    folder: Path
    artwork: ArtworkPlan
    rename_to: Path | None
    expected: dict
    flac_paths: set[Path]
    edits: list
    lines: list[str]
    catalog_update: tuple | None
    unchanged: int
    tag_example: list[str]

    @classmethod
    def build(cls, tagger, clear_tags, reserved_folders):
        folder = tagger.folderpath
        cover = tagger.config.cover
        artwork = ArtworkPlan.build(folder, tagger.artworkpath, cover.clear_existing_artwork, cover.retain_existing_artwork)
        lines = list(artwork.describe())
        expected = dict(artwork.expected)
        rename_to = tagger.folder._standardized_folder_path(tagger.etreerec)
        if rename_to is not None:
            if rename_to in reserved_folders or os.path.lexists(rename_to):
                lines.append(f"  Warning: folder rename skipped because {rename_to} is occupied")
                rename_to = None
            else:
                lines.append(f"  Rename folder to {rename_to}")
                expected[rename_to] = None

        loaded = []
        flac_paths = set()
        for file in tagger.folder.musicfiles:
            path = Path(file.path)
            flac_paths.add(path)
            expected[path] = file_state(path)
            loaded.append((file, FLAC(file.path)))
        tracks = None
        catalog_update = None
        album = tagger._album_title()
        if not tagger.etreerec.tracks:
            tracks, records = _local_tracks(tagger, loaded)
            catalog_update = (tagger.repository, tagger.etreerec.id, records, tagger.etreerec.md5key)
            lines.append(f"  Import {len(records)} tracks into SQLite for SHNID {tagger.etreerec.id}")
        args_list, dates = tagger._file_tag_arguments(
            album, str(artwork.destination) if artwork.destination else None,
            clear_tags, tracks=tracks,
        )

        edits = []
        tag_example = []
        sample_index = next((index for index, args in enumerate(args_list) if args[-1]), 0)
        for index, ((file, audio), args) in enumerate(zip(loaded, args_list, strict=True)):
            old_tags = _tags(audio)
            old_pictures = [picture.write() for picture in audio.pictures]
            prepare_file_tags(audio, args, dates, image_data=artwork.image)
            new_tags = _tags(audio)
            if index == sample_index:
                prefs = tagger.config.preferences
                title = next(iter(new_tags.get("title", [])), "Unavailable")
                tag_example = [
                    f"Example FLAC tags for {folder.name}/{file.name}",
                    f"  Album: {album}",
                    f"  Song title: {title}",
                    f"  Write DATE tag: {'Yes' if prefs.write_date else 'No'}",
                    f"  Write separate YEAR, MONTH, and DAY tags: {'Yes' if prefs.write_date_parts else 'No'}",
                    f"  Clear existing tags: {'Yes' if clear_tags else 'No'}",
                ]
            changes = [
                f"    {key.upper()}: {old_tags.get(key)!r} -> {new_tags.get(key)!r}"
                for key in sorted(old_tags.keys() | new_tags.keys())
                if old_tags.get(key) != new_tags.get(key)
            ]
            if old_pictures != [picture.write() for picture in audio.pictures]:
                action = f"Replace {len(old_pictures)} embedded picture(s) with" if old_pictures else "Embed"
                changes.append(f"    {action} front cover from {artwork.source}")
            if changes:
                lines.extend([f"  {args[1]}", *changes])
                edits.append(audio)
        unchanged = len(loaded) - len(edits)
        if unchanged:
            lines.append(f"  {unchanged} FLAC(s) already tagged per preferences")
        if (edits or artwork.replace) and any(folder.glob("*.md5")):
            lines.append("  Warning: whole-file MD5 manifests may become stale")
        return cls(folder, artwork, rename_to, expected, flac_paths, edits, lines, catalog_update, unchanged, tag_example)

    @property
    def has_changes(self):
        return bool(self.edits or self.artwork.replace or self.rename_to or self.catalog_update)

    def apply(self):
        if (
            set(self.folder.glob("*.flac")) != self.flac_paths
            or any(file_state(path) != state for path, state in self.expected.items())
        ):
            logger.warning("Skipped %s because files or destinations changed after preview", self.folder)
            return False
        self.artwork.apply()
        for audio in self.edits:
            audio.save()
        if self.catalog_update:
            repository, shnid, records, md5key = self.catalog_update
            repository.overwrite_tracks(shnid, records, md5key=md5key)
        if self.rename_to:
            _rename_show(self.folder, self.rename_to)
        return True


def _print_tagging_results(updated, current, failed):
    print("\nTagging results")
    print(f"  Updated: {updated}")
    print(f"  Already tagged per preferences: {current}")
    print(f"  Failed: {failed}")


def preview_and_apply(folders, make_tagger, clear_tags, manifest_path, database):
    plans = []
    details = []
    issues = []
    failed = 0
    skipped = 0
    reserved = set(folders)
    folders = list(dict.fromkeys(folders))
    for folder in folders:
        try:
            tagger = make_tagger(folder)
            if tagger.errormsg:
                skipped += 1
                reason = "No catalog recording matched the audio fingerprints." if tagger.NoMatch else tagger.errormsg
                issues.append((folder.name, reason))
                continue
            plan = ShowPlan.build(tagger, clear_tags, reserved)
            if plan.rename_to:
                reserved.add(plan.rename_to)
            plans.append(plan)
            details.extend([str(folder), *(plan.lines or ["  No changes"]), ""])
        except Exception as exc:
            failed += 1
            logger.exception("Could not plan changes for %s", folder)
            issues.append((folder.name, str(exc) or type(exc).__name__))

    pending = [plan for plan in plans if plan.has_changes]
    current = len(plans) - len(pending)
    remote_shnids = database.pending_remote_shnids
    if not pending and not remote_shnids:
        _print_tagging_results(0, current, skipped + failed)
        print("\nNo changes detected.")
        return not failed

    summary = [
        f"Tagging preview for {len(folders)} show(s)",
        f"",
        f"  Will change: {len(pending)}",
        f"  Already tagged per preferences: {current}",
        f"  Expected to fail: {skipped + failed}",
    ]
    for name, reason in issues:
        summary.extend(["", f"    - {name}"])
        summary.extend(f"      {line}" for line in reason.splitlines())
    tag_example = next((plan.tag_example for plan in pending if plan.tag_example), None)
    if tag_example is None:
        tag_example = next((plan.tag_example for plan in plans if plan.tag_example), [])
    if tag_example:
        summary.extend(["", *tag_example])
    catalog_lines = []
    if remote_shnids:
        ids = ", ".join(map(str, remote_shnids))
        catalog_lines = [f"Import Etree catalog matches and fingerprints for SHNIDs {ids}", ""]
    with manifest_path.open("x", encoding="utf-8") as manifest:
        manifest.write("\n".join([*summary, "", *catalog_lines, *details, ""]))
    print("\n".join(summary))
    print()
    print(f"Change manifest: {manifest_path.resolve()}", flush=True)
    try:
        print()
        approved = input('Review the manifest. Type "yes" to apply or anything else to cancel: ') == "yes"
    except (EOFError, KeyboardInterrupt):
        approved = False
        print()
    if not approved:
        print()
        print("Cancelled. No planned changes were applied.")
        return not failed

    if remote_shnids:
        database.conn.commit()

    applied = 0
    for plan in pending:
        try:
            if plan.apply():
                applied += 1
                if plan.rename_to and manifest_path.resolve().is_relative_to(plan.folder):
                    manifest_path = plan.rename_to / manifest_path.resolve().relative_to(plan.folder)
                    print(f"Change manifest moved to {manifest_path}")
            else:
                skipped += 1
        except Exception:
            failed += 1
            logger.exception("Could not finish applying %s. Some changes may have been saved.", plan.folder)
    _print_tagging_results(applied, current, skipped + failed)
    return not failed
