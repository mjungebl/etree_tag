import sys
from pathlib import Path
import pytest

# ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tagger import ConcertTagger


def _make_tagger(folders, defaults):
    tagger = ConcertTagger.__new__(ConcertTagger)
    tagger.artwork_folders = folders
    tagger.default_images_map = defaults
    return tagger


def test_find_artwork_from_folder(tmp_path: Path):
    art_dir = tmp_path / "art" / "1975"
    art_dir.mkdir(parents=True)
    art_file = art_dir / "gd1975-03-23.jpg"
    art_file.write_text("dummy")

    tagger = _make_tagger(
        [str(tmp_path / "art")], {"gd": str(tmp_path / "default.jpg")}
    )
    result = tagger._find_artwork("gd", "1975-03-23")
    assert result == art_file


def test_find_artwork_default(tmp_path: Path):
    default = tmp_path / "default.jpg"
    default.write_text("img")
    tagger = _make_tagger([str(tmp_path / "art")], {"gd": str(default)})
    result = tagger._find_artwork("gd", "1975-03-23")
    assert result == default


def test_find_artwork_missing_default(tmp_path: Path):
    tagger = _make_tagger(
        [str(tmp_path / "art")], {"gd": str(tmp_path / "default.jpg")}
    )
    with pytest.raises(FileNotFoundError):
        tagger._find_artwork("gd", "1975-03-23")


def test_find_artwork_no_default(tmp_path: Path):
    tagger = _make_tagger([str(tmp_path / "art")], {})
    result = tagger._find_artwork("gd", "1975-03-23")
    assert result is None


def test_stage_artwork_keeps_first_backup_on_repeated_replacement(tmp_path):
    tagger = _make_tagger([], {})
    tagger.folderpath = tmp_path
    tagger.artworkpath = tmp_path / "source.jpg"
    cover = tmp_path / "folder.jpg"
    backup = tmp_path / "folder.jpg.old"
    cover.write_bytes(b"original")

    for image in (b"first replacement", b"second replacement"):
        tagger.artworkpath.write_bytes(image)
        assert tagger._stage_artwork(True, True) == str(cover)
        assert cover.read_bytes() == image
        assert backup.read_bytes() == b"original"

    cover_stat = cover.stat()
    assert tagger._stage_artwork(True, True) == str(cover)
    assert cover.stat().st_mtime_ns == cover_stat.st_mtime_ns
    assert list(tmp_path.glob("folder.jpg.old*")) == [backup]
