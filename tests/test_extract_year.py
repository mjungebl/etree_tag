from tagger import extract_year


def test_extract_year_iso():
    assert extract_year("1975-06-21") == 1975


def test_extract_year_partial_dashes():
    assert extract_year("1975-XX-XX") == 1975


def test_extract_year_partial_question():
    assert extract_year("??/??/75") == 1975
