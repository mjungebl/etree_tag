"""Utilities for compressing and extracting archives."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
import zipfile
from typing import Iterable, Tuple

try:
    import rarfile
except Exception:  # pragma: no cover - rarfile is optional
    rarfile = None


def _is_hidden(name: str) -> bool:
    """Return True if any component of *name* looks like a hidden/system file."""
    parts = Path(name).parts
    for p in parts:
        if p.startswith(".") or p.startswith("__MACOSX"):
            return True
    return False


def _root_folder_if_single(names: list[str]) -> str | None:
    """Return the single top-level folder in *names* or ``None``."""
    root = None
    for name in names:
        if _is_hidden(name):
            continue
        parts = Path(name).parts
        if len(parts) == 1:
            # A single path component could be a directory entry in the
            # archive (e.g. ``folder/``). When the entry does not end with a
            # path separator it's a file at the archive root, which means
            # there's no single parent folder.
            if not name.endswith(('/', '\\')):
                return None
            candidate = parts[0]
        else:
            candidate = parts[0]
        if root is None:
            root = candidate
        elif root != candidate:
            return None
    return root


def _collect_directory_info(names: Iterable[str], root: str | None) -> tuple[set[Path], set[Path]]:
    """Return expected and skipped directories from *names*.

    Parameters
    ----------
    names:
        Iterable of archive member names.
    root:
        Optional root folder returned by :func:`_root_folder_if_single`.

    Returns
    -------
    tuple
        ``(expected, skipped)`` where each item is a set of :class:`Path`
        objects relative to the destination directory. ``skipped`` contains
        directories ignored because they are hidden.
    """
    expected: set[Path] = set()
    skipped: set[Path] = set()
    for name in names:
        path = Path(name)
        parts = list(path.parts)
        if root and parts and parts[0] == root:
            parts = parts[1:]
        if not parts:
            continue
        rel_path = Path(*parts)
        is_hidden = _is_hidden(name)
        # include the directory itself for explicit dir entries
        if name.endswith(("/", "\\")):
            target = rel_path
            if is_hidden:
                skipped.add(target)
            else:
                expected.add(target)
        for parent in rel_path.parents:
            if parent == Path("."):
                continue
            if is_hidden:
                skipped.add(parent)
            else:
                expected.add(parent)
    return expected, skipped


def _extract_member(reader, member, dest: Path, overwrite: bool) -> None:
    """Extract a single archive member to *dest* respecting *overwrite*."""
    target = dest / member.filename
    if hasattr(member, "is_dir"):
        is_directory = member.is_dir()  # zipfile
    else:
        is_directory = member.isdir()  # rarfile
    if is_directory:
        target.mkdir(parents=True, exist_ok=True)
        return
    if target.exists() and not overwrite:
        msg = f"File {target} already exists; skipping extraction."
        logging.error(msg)
        print(msg)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with reader.open(member) as src, open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)


def extract_archives(directory: str | Path, target: str | Path | None = None, overwrite: bool = False) -> None:
    """Unpack all ``.zip`` and ``.rar`` files in ``directory``.

    Parameters
    ----------
    directory:
        Folder containing archives to extract.
    target:
        Optional destination folder. Defaults to ``directory``.
    overwrite:
        If ``True``, existing files are replaced. Otherwise extraction of
        conflicting files is skipped and logged.
    """
    directory = Path(directory)
    dest_base = Path(target) if target else directory

    for item in directory.iterdir():
        if not item.is_file():
            continue
        ext = item.suffix.lower()
        if ext not in {".zip", ".rar"}:
            continue
        try:
            if ext == ".zip":
                with zipfile.ZipFile(item) as archive:
                    names = archive.namelist()
                    root = _root_folder_if_single(names)
                    dest = dest_base if root else dest_base / item.stem
                    if dest != dest_base:
                        dest.mkdir(parents=True, exist_ok=True)
                    expected, skipped = _collect_directory_info(names, root)
                    for member in archive.infolist():
                        if _is_hidden(member.filename):
                            continue
                        base_dest = dest_base if root else dest
                        _extract_member(archive, member, base_dest, overwrite)
            else:  # rar file
                if rarfile is None:
                    raise RuntimeError("rarfile module is required for RAR archives")
                with rarfile.RarFile(item) as archive:
                    names = [m.filename for m in archive.infolist()]
                    root = _root_folder_if_single(names)
                    dest = dest_base if root else dest_base / item.stem
                    if dest != dest_base:
                        dest.mkdir(parents=True, exist_ok=True)
                    expected, skipped = _collect_directory_info(names, root)
                    for member in archive.infolist():
                        if _is_hidden(member.filename):
                            continue
                        base_dest = dest_base if root else dest
                        _extract_member(archive, member, base_dest, overwrite)

            # validate directories
            missing = [d for d in expected if not (dest / d).is_dir()]
            if missing:
                logging.warning(
                    f"Missing directories after extracting {item.name}: {missing}"
                )
            if skipped:
                logging.info(
                    f"Skipped directories from {item.name}: {sorted(skipped)}"
                )
        except Exception as e:  # pragma: no cover - errors logged
            logging.error(f"Failed to extract {item}: {e}")
            print(f"Error extracting {item}: {e}")
