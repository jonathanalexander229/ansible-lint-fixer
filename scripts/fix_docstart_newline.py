#!/usr/bin/env python3
"""
Fix YAML document start and final newline.

Ensures the first non-empty line is '---' and that the file ends
with a newline. Only modifies files when changes are needed.

Usage:
  scripts/fix_docstart_newline.py path1.yml [path2.yaml|dir ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, ensure_document_start, ensure_final_newline  # type: ignore


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)

    lines, changed_doc = ensure_document_start(lines)
    content = '\n'.join(lines)
    content, changed_nl = ensure_final_newline(content)

    if changed_doc or changed_nl:
        path.write_text(content, encoding='utf-8')
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description='Ensure YAML has document start (---) and a final newline.')
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

