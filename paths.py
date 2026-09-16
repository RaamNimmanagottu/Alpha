"""Resolves the project root correctly whether running as a plain script or as a
cx_Freeze/PyInstaller frozen executable.

`Path(__file__).resolve().parent` breaks once frozen: __file__ then points inside
the bundled library zip, not to the folder the .exe actually lives in on disk. The
standard fix (both cx_Freeze and PyInstaller set sys.frozen = True) is to use
sys.executable's directory instead in that case.
"""
from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent
