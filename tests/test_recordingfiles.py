import types
import sys
from pathlib import Path

# ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide a minimal stub for the mutagen.flac module used by recordingfiles
mutagen = types.ModuleType('mutagen')
flac_mod = types.ModuleType('mutagen.flac')
class DummyInfo:
    length = 0
    md5_signature = b''
    bits_per_sample = 16
    sample_rate = 44100
    channels = 2
class DummyFLAC:
    def __init__(self, path):
        self.info = DummyInfo()
    def __contains__(self, item):
        return False
    def __getitem__(self, item):
        raise KeyError
flac_mod.FLAC = DummyFLAC
flac_mod.Picture = object
mutagen.flac = flac_mod
sys.modules.setdefault('mutagen', mutagen)
sys.modules.setdefault('mutagen.flac', flac_mod)

from recordingfiles import RecordingFolder


def _create_sample_files(base: Path, info_name='info.txt'):
    (base / info_name).write_text('info contents', encoding='utf-8')
    (base / 'example.ffp').write_text('fingerprint data', encoding='utf-8')
    (base / 'checks.st5').write_text('checksum data', encoding='utf-8')


def test_read_methods_with_info_keyword(tmp_path: Path):
    _create_sample_files(tmp_path)
    rec = RecordingFolder(str(tmp_path))
    assert rec.read_info() == 'info contents'
    assert rec.read_fingerprint() == 'fingerprint data'
    assert rec.read_checksums() == 'checksum data'


def test_fallback_txt_detection(tmp_path: Path):
    _create_sample_files(tmp_path, info_name='notes.txt')
    rec = RecordingFolder(str(tmp_path))
    # Should fall back to the only txt file
    assert rec.info_file.name == 'notes.txt'
    assert rec.read_info() == 'info contents'
