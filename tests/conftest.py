from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# Ensure the project root is importable before tests import application modules.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _DummyInfo:
    length = 0
    md5_signature = b""
    bits_per_sample = 16
    sample_rate = 44100
    channels = 2


class _DummyFLAC:
    def __init__(self, path: str):
        # path kept for parity with real mutagen objects
        self.path = path
        self.info = _DummyInfo()

    def __contains__(self, item: str) -> bool:
        return False

    def __getitem__(self, key: str):
        raise KeyError(key)


# Stub external modules that the application imports.
mutagen_mod = types.ModuleType("mutagen")
mutagen_flac_mod = types.ModuleType("mutagen.flac")
mutagen_flac_mod.FLAC = _DummyFLAC
mutagen_flac_mod.Picture = object
mutagen_mod.flac = mutagen_flac_mod
sys.modules.setdefault("mutagen", mutagen_mod)
sys.modules.setdefault("mutagen.flac", mutagen_flac_mod)

tqdm_mod = types.ModuleType("tqdm")
tqdm_mod.tqdm = lambda iterable=None, **_: iterable
sys.modules.setdefault("tqdm", tqdm_mod)


@pytest.fixture
def info_tagger():
    from InfoFileTagger_class import FlacInfoFileTagger

    return FlacInfoFileTagger(also_log_to_console=False)
