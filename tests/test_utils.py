import sqlite3
import types
import sys
import pytest

# Provide dummy mutagen modules so InfoFileTagger can be imported without the
# real dependency being installed.
mutagen = types.ModuleType("mutagen")
mutagen.flac = types.ModuleType("flac")
mutagen.flac.FLAC = object
sys.modules.setdefault("mutagen", mutagen)
sys.modules.setdefault("mutagen.flac", mutagen.flac)

from InfoFileTagger import strip_after_n_spaces
from sqliteetreedb import SQLiteEtreeDB


def test_strip_after_n_spaces_basic():
    assert strip_after_n_spaces('hello  world', 2) == 'hello'


def test_strip_after_n_spaces_no_change():
    text = 'hello world'
    assert strip_after_n_spaces(text, 2) == text


def test_strip_after_n_spaces_leading_spaces():
    text = '  leading  spaces'
    assert strip_after_n_spaces(text, 2) == text


def test_get_signatures_by_md5key_returns_rows():
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    cursor.execute(
        'CREATE TABLE signatures (shnid INTEGER, md5key INTEGER, base_filename TEXT, file_extension TEXT, audio_checksum TEXT, PRIMARY KEY (shnid, md5key, base_filename, file_extension))'
    )
    sample_row = (1, 42, 'track1', 'flac', 'abc')
    cursor.execute(
        'INSERT INTO signatures (shnid, md5key, base_filename, file_extension, audio_checksum) VALUES (?, ?, ?, ?, ?)',
        sample_row,
    )
    conn.commit()

    db = SQLiteEtreeDB.__new__(SQLiteEtreeDB)
    db.conn = conn
    db.cursor = conn.cursor()

    rows = db.get_signatures_by_md5key(1)
    assert rows == [sample_row]
