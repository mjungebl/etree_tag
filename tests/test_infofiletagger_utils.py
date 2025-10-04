import types
import sys
from pathlib import Path
from InfoFileTagger import (
    is_valid_date,
    file_sort_key,
    strip_after_n_spaces,
    clean_track_name,
)
# ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide a minimal stub for the mutagen.flac module used by InfoFileTagger
mutagen = types.ModuleType("mutagen")
flac_mod = types.ModuleType("mutagen.flac")
flac_mod.FLAC = object
flac_mod.Picture = object
mutagen.flac = flac_mod
sys.modules.setdefault("mutagen", mutagen)
sys.modules.setdefault("mutagen.flac", flac_mod)




def test_is_valid_date_true():
    assert is_valid_date("2025-07-05")
    assert is_valid_date("07-05-25")
    assert is_valid_date("07/05/2025")


def test_is_valid_date_false():
    assert not is_valid_date("not a date")
    assert not is_valid_date("2025-13-01")


def test_file_sort_key_parsing():
    assert file_sort_key("foo/d1t02.flac") == (1, 2)
    assert file_sort_key("bar/s3t10.wav") == (3, 10)


def test_file_sort_key_fallback():
    disc, track = file_sort_key("foo/bar.flac")
    assert disc == float("inf")
    assert track == "bar"


def test_strip_after_n_spaces():
    assert strip_after_n_spaces("hello     world", 5) == "hello"
    assert strip_after_n_spaces("hello   world", 5) == "hello   world"


def test_clean_track_name_basic():
    assert clean_track_name("e: Dark Star") == "Dark Star"
    assert clean_track_name("Drums->Space") == "Drums > Space"
    assert clean_track_name("Encore: Ripple") == "Ripple"
