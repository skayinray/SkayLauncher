#!/usr/bin/env python3
"""SkayLauncher entry point for source runs and packaged builds."""

from __future__ import annotations

import sys
from pathlib import Path

source_path = Path(__file__).resolve().parent / "src"
if source_path.is_dir() and str(source_path) not in sys.path:
    sys.path.insert(0, str(source_path))

from skaylauncher.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
