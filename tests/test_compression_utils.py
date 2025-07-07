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
