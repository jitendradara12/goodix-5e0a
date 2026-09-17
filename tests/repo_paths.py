"""Checkout-local paths, including the whitebox test's archived helper."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEGACY_EXPERIMENTS_DIR = REPO_ROOT / "legacy-experiments"

if LEGACY_EXPERIMENTS_DIR.is_dir() and str(LEGACY_EXPERIMENTS_DIR) not in sys.path:
    sys.path.insert(0, str(LEGACY_EXPERIMENTS_DIR))


def repo(*parts):
    """Repo-relative path as str: repo('libfprint-driver', 'goodix5e0a.c')."""
    return str(REPO_ROOT.joinpath(*parts))

