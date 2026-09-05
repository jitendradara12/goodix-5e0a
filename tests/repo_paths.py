"""Portable paths for the Goodix 27c6:5e0a test suite.

Replaces hardcoded machine paths (e.g. /home/sastauser/code/temp/goodix).
REPO_ROOT always resolves; BUILD_TREE / NIXOS_MODULE_DIR point at optional
external trees and tests using them must skipUnless they exist.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_TREE = Path("/tmp/libfprint-goodix")
NIXOS_MODULE_DIR = Path("/home/sastauser/NixOS-Hyprland/modules/goodix")


def repo(*parts):
    """Repo-relative path as str: repo('libfprint-driver', 'goodix5e0a.c')."""
    return str(REPO_ROOT.joinpath(*parts))
