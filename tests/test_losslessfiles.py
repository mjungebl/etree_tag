from losslessfiles import ffp, md5, parse_flac_fingerprint, parse_md5


def test_parse_flac_fingerprint_basic():
    content = """
; comment line
track01.flac:abcdef123456
subdir\\track02.flac:DEADBEEF
"""
    result = parse_flac_fingerprint(content)
    assert result == [
        ("track01.flac", "abcdef123456"),
        ("subdir\\track02.flac", "DEADBEEF"),
    ]


def test_readffpfile_populates_signatures(tmp_path):
    folder = tmp_path / "music"
    folder.mkdir()
    ffp_path = folder / "checks.ffp"
    ffp_path.write_text(
        "track01.flac:abcdef\n"
        "subdir\\track02.flac:DEADBEEF\n"
        "; ignored comment\n"
    )

    checker = ffp(str(folder), "checks.ffp")
    checker.readffpfile()

    assert checker.signatures == {
        "track01.flac": "abcdef",
        "subdir/track02.flac": "DEADBEEF",
    }
    assert checker.errors == []


def test_parse_md5_basic():
    content = """
; header
ABCDEF1234567890ABCDEF1234567890 *track01.flac
1234567890ABCDEF foo/bar.flac
"""
    result = parse_md5(content)
    assert result == [
        ("track01.flac", "ABCDEF1234567890ABCDEF1234567890"),
        ("foo/bar.flac", "1234567890ABCDEF"),
    ]


def test_readmd5file_populates_signatures(tmp_path):
    folder = tmp_path / "show"
    folder.mkdir()
    md5_path = folder / "checks.md5"
    md5_path.write_text(
        "ABCDEF1234567890 track01.flac\n"
        "1234567890ABCDEF *sub\\dir\\track02.flac\n"
    )

    checker = md5(str(folder), "checks.md5", signatures={})
    checker.readmd5file()

    assert checker.signatures == {
        "track01.flac": "ABCDEF1234567890",
        "sub/dir/track02.flac": "1234567890ABCDEF",
    }
    assert checker.errors == []
