from InfoFileTagger_class import FlacInfoFileTagger


def test_is_valid_date_true(info_tagger):
    assert info_tagger.is_valid_date("2025-07-05")
    assert info_tagger.is_valid_date("07-05-25")
    assert info_tagger.is_valid_date("07/05/2025")


def test_is_valid_date_false(info_tagger):
    assert not info_tagger.is_valid_date("not a date")
    assert not info_tagger.is_valid_date("2025-13-01")


def test_file_sort_key_parsing():
    assert FlacInfoFileTagger.file_sort_key("foo/d1t02.flac") == (1, 2)
    assert FlacInfoFileTagger.file_sort_key("bar/s3t10.wav") == (3, 10)


def test_file_sort_key_fallback():
    disc, track = FlacInfoFileTagger.file_sort_key("foo/bar.flac")
    assert disc == float("inf")
    assert track == "bar"


def test_strip_after_n_spaces(info_tagger):
    assert info_tagger.strip_after_n_spaces("hello     world", 5) == "hello"
    assert info_tagger.strip_after_n_spaces("hello   world", 5) == "hello   world"


def test_clean_track_name_basic(info_tagger):
    assert info_tagger.clean_track_name("e: Dark Star") == "Dark Star"
    assert info_tagger.clean_track_name("Drums->Space") == "Drums > Space"
    assert info_tagger.clean_track_name("Encore: Ripple") == "Ripple"
