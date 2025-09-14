#!/usr/bin/env python3
"""
Remove trailing spaces and tabs from YAML files.

Keeps indentation intact and only strips whitespace at end-of-line.
Does not alter final newline state (use docstart/newline fixer for that).

Usage:
  scripts/fix_trailing_spaces.py FILE_OR_DIR [...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files  # type: ignore


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)
    fixed_lines: List[str] = [ln.rstrip(' \t') for ln in lines]
    new_content = '\n'.join(fixed_lines)

    # Preserve original final newline presence
    if original.endswith('\n') and not new_content.endswith('\n'):
        new_content += '\n'

    if new_content != original:
        path.write_text(new_content, encoding='utf-8')
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description='Strip trailing spaces/tabs from YAML files.')
    ap.add_argument('paths', nargs='+', help='Files or directories to process')
    args = ap.parse_args()

    changed = 0
    checked = 0
    for file in iter_yaml_files(args.paths):
        checked += 1
        try:
            if fix_file(file):
                print(f"Fixed: {file}")
                changed += 1
            else:
                print(f"No change: {file}")
        except Exception as exc:
            print(f"Error: {file}: {exc}")
            return 2

    if checked == 0:
        print('No YAML files found in provided paths.')
        return 1

    print(f"Summary: {changed} changed, {checked} checked")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

