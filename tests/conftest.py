from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# Ensure the project root is importable before tests import application modules.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


tqdm_mod = types.ModuleType("tqdm")
tqdm_mod.tqdm = lambda iterable=None, **_: iterable
sys.modules.setdefault("tqdm", tqdm_mod)


@pytest.fixture
def info_tagger():
    from InfoFileTagger_class import FlacInfoFileTagger

    return FlacInfoFileTagger(also_log_to_console=False)
