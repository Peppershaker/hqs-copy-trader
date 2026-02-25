#!/usr/bin/env python3
"""
build.py – Generate and run PyInstaller spec for DAS Copy Trader

Usage:  python scripts/build.py --das-bridge-dir /path/to/das-bridge --static-dir /path/to/static
"""

import argparse
import os
import sys
from pathlib import Path

import PyInstaller.__main__

parser = argparse.ArgumentParser()
parser.add_argument(
    "--das-bridge-dir", required=True, help="Path to das-bridge repo root"
)
parser.add_argument(
    "--static-dir", required=True, help="Path to static frontend directory"
)
args = parser.parse_args()

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
MAIN_SCRIPT = BACKEND_DIR / "app" / "main.py"
DAS_BRIDGE_SRC = Path(args.das_bridge_dir) / "src" / "das_bridge"
STATIC_DIR = Path(args.static_dir)

if not MAIN_SCRIPT.exists():
    print(f"ERROR: main.py not found at {MAIN_SCRIPT}")
    sys.exit(1)
if not DAS_BRIDGE_SRC.exists():
    print(f"ERROR: das_bridge source not found at {DAS_BRIDGE_SRC}")
    sys.exit(1)
if not STATIC_DIR.exists():
    print(f"ERROR: static dir not found at {STATIC_DIR}")
    sys.exit(1)

# PyInstaller options
opts = [
    str(MAIN_SCRIPT),
    "--name=DASCopyTrader",
    "--one-dir",
    "--windowed",
    "--add-data",
    f"{DAS_BRIDGE_SRC}{os.pathsep}das_bridge",
    "--add-data",
    f"{STATIC_DIR}{os.pathsep}app/static",
    "--hidden-import",
    "das_bridge",
    "--hidden-import",
    "dotenv",
    "--collect-all",
    "das_bridge",
    "--collect-submodules",
    "das_bridge",
    "--collect-data",
    "das_bridge",
    "--noconfirm",
    "--clean",
    "--distpath",
    str(BACKEND_DIR / "dist"),
]

print("Running PyInstaller with options:")
for o in opts:
    print("  ", o)

PyInstaller.__main__.run(opts)
