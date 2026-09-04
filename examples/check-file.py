#!/usr/bin/env python3
"""Offline checker example: 0 when a marker exists, 1 while absent; not a model probe."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    print("usage: check-file.py MARKER", file=sys.stderr)
    raise SystemExit(2)
raise SystemExit(0 if Path(sys.argv[1]).is_file() else 1)
