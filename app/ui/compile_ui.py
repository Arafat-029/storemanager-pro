#!/usr/bin/env python3
"""
Compile all .ui files in this directory to Python modules.

Run from the store_management directory:
    python -m app.ui.compile_ui

Or directly:
    python app/ui/compile_ui.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

UI_DIR = Path(__file__).parent
OUT_DIR = UI_DIR / "compiled"
OUT_DIR.mkdir(exist_ok=True)

(OUT_DIR / "__init__.py").touch()

ui_files = list(UI_DIR.glob("*.ui"))
if not ui_files:
    print("No .ui files found.")
    sys.exit(0)

ok = errors = 0
for ui_file in sorted(ui_files):
    out_file = OUT_DIR / f"{ui_file.stem}_ui.py"
    result = subprocess.run(
        ["pyside6-uic", str(ui_file), "-o", str(out_file)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"  ✓  {ui_file.name}  →  compiled/{out_file.name}")
        ok += 1
    else:
        print(f"  ✗  {ui_file.name}: {result.stderr.strip()}")
        errors += 1

print(f"\n{ok} compiled, {errors} error(s).")
