#!/usr/bin/env python3
"""Compatibility entry point for the canonical master-workbook generator."""

from __future__ import annotations

import sys
from pathlib import Path

# Permit direct execution as ``python scripts/export_excel_architecture.py``.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generate_english_master_workbook import main


if __name__ == "__main__":
    main()
