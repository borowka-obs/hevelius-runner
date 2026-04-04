import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_hevelius_runner():
    path = SRC / "hevelius-runner.py"
    spec = importlib.util.spec_from_file_location("hevelius_runner", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def runner_mod():
    return load_hevelius_runner()
