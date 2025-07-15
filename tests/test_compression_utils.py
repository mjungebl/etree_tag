import sys
from pathlib import Path
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compression_utils import extract_archives


def _make_zip(zip_path: Path, files: dict[str, str]):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_extract_single_folder(tmp_path: Path):
    zdir = tmp_path / "z"
    zdir.mkdir()
    zip_path = zdir / "sample.zip"
    _make_zip(zip_path, {"folder/file.txt": "data"})

    extract_archives(zdir)

    assert (zdir / "folder" / "file.txt").read_text() == "data"


def test_extract_with_new_folder(tmp_path: Path):
    zdir = tmp_path / "z"
    zdir.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    zip_path = zdir / "mixed.zip"
    _make_zip(zip_path, {"a.txt": "x", "sub/b.txt": "y"})

    extract_archives(zdir, target=out)

    assert (out / "mixed" / "a.txt").read_text() == "x"
    assert (out / "mixed" / "sub" / "b.txt").read_text() == "y"


def test_overwrite(tmp_path: Path):
    zdir = tmp_path / "z"
    zdir.mkdir()
    zip_path = zdir / "dup.zip"
    _make_zip(zip_path, {"folder/file.txt": "new"})

    dest = tmp_path / "dest"
    (dest / "folder").mkdir(parents=True)
    (dest / "folder" / "file.txt").write_text("old")

    extract_archives(zdir, target=dest)
    assert (dest / "folder" / "file.txt").read_text() == "old"

    extract_archives(zdir, target=dest, overwrite=True)
    assert (dest / "folder" / "file.txt").read_text() == "new"


def test_zip_with_directory_entry(tmp_path: Path):
    """Zip files may contain an explicit folder entry."""
    zdir = tmp_path / "z"
    zdir.mkdir()
    zip_path = zdir / "f.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("folder/", "")
        zf.writestr("folder/a.txt", "A")
        zf.writestr("folder/b.txt", "B")

    extract_archives(zdir)

    assert (zdir / "folder" / "a.txt").read_text() == "A"
    assert (zdir / "folder" / "b.txt").read_text() == "B"


def test_extract_backslash_paths(tmp_path: Path):
    """Paths with backslashes should be normalized."""
    zdir = tmp_path / "z"
    zdir.mkdir()
    zip_path = zdir / "bs.zip"
    _make_zip(zip_path, {"dir\\sub\\file.txt": "X"})

    extract_archives(zdir)

    assert (zdir / "dir" / "sub" / "file.txt").read_text() == "X"


def test_root_with_backslashes(tmp_path: Path):
    zdir = tmp_path / "z"
    zdir.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    zip_path = zdir / "root.zip"
    _make_zip(zip_path, {"root\\a.txt": "A"})

    extract_archives(zdir, target=out)

    assert (out / "root" / "a.txt").read_text() == "A"


def test_trailing_space_in_folder_name(tmp_path: Path):
    """Folder names ending with spaces should be normalized."""
    zdir = tmp_path / "z"
    zdir.mkdir()
    zip_path = zdir / "space.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("folder /", "")
        zf.writestr("folder /file.txt", "X")

    extract_archives(zdir)

    assert (zdir / "folder" / "file.txt").read_text() == "X"


def test_quotes_in_file_name(tmp_path: Path):
    """Double quotes in file names should be stripped."""
    zdir = tmp_path / "z"
    zdir.mkdir()
    zip_path = zdir / "quote.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr('folder/"a".txt', "Q")

    extract_archives(zdir)

    assert (zdir / "folder" / "a.txt").read_text() == "Q"
