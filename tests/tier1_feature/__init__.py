"""Tier 1: Feature Coverage Test Suite (Features F01 - F25, M1 - M2)."""
import sys
from pathlib import Path

_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
