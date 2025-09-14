#!/usr/bin/env python3
"""
Fix indentation and simple quote issues in YAML files.

Indentation:
  - Converts leading tabs to spaces.
  - Normalizes indentation to multiples of --indent-size (default 2).

Quotes:
  - Unquotes when: expressions like "...{{ var }}..." -> when: ...{{ var }}...
  - Unquotes Jinja variables after ':' like ": "{{ var }}"" -> ": {{ var }}"
  - Unquotes simple booleans/numbers after ':' like ": "true"" -> ": true"

Usage:
  scripts/fix_indent_quotes.py [--indent-size N] FILE_OR_DIR [...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, split_code_and_comment  # type: ignore


def fix_indentation(line: str, indent_size: int) -> str:
    if not line.strip():
        return line

    # Extract leading whitespace
    i = 0
    while i < len(line) and line[i] in (' ', '\t'):
        i += 1
    leading = line[:i]
    rest = line[i:]

    # Convert tabs to spaces (tab = indent_size spaces)
    spaces = 0
    for ch in leading:
        spaces += indent_size if ch == '\t' else 1

    # Normalize to nearest multiple of indent_size
    if indent_size <= 0:
        indent_size = 2

    if spaces % indent_size != 0:
        correct = (spaces // indent_size) * indent_size
        if spaces - correct > indent_size // 2:
            correct += indent_size
    else:
        correct = spaces

    return ' ' * correct + rest


def fix_quotes(line: str) -> str:
    code, comment = split_code_and_comment(line)
    if code.lstrip().startswith('#'):
        return line  # keep full-line comments unchanged

    # 1) Unquote when: "...{{ ... }}..."
    code = re.sub(r'when:\s*"([^"]*\{\{[^}]*\}\}[^"]*)"', r'when: \1', code)

    # 2) Unquote simple Jinja variable after ':'
    code = re.sub(r':\s*"(\{\{[^}]*\}\})"', r': \1', code)

    # 3) Unquote simple booleans/numbers after ':'
    code = re.sub(r':\s*"(true|false|\d+)"', r': \1', code)

    return code + comment


def fix_file(path: Path, indent_size: int) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)

    fixed_lines: List[str] = []
    for ln in lines:
        ln2 = fix_indentation(ln, indent_size)
        ln3 = fix_quotes(ln2)
        fixed_lines.append(ln3)

    new_content = '\n'.join(fixed_lines)
    if new_content != original:
        # Preserve original final newline presence
        if original.endswith('\n') and not new_content.endswith('\n'):
            new_content += '\n'
        path.write_text(new_content, encoding='utf-8')
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description='Fix indentation and simple quote issues in YAML files.')
    ap.add_argument('--indent-size', type=int, default=2, help='Indentation size (spaces). Default: 2')
    ap.add_argument('paths', nargs='+', help='Files or directories to process')
    args = ap.parse_args()

    changed = 0
    checked = 0
    for file in iter_yaml_files(args.paths):
        checked += 1
        try:
            if fix_file(file, args.indent_size):
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

