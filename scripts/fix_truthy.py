#!/usr/bin/env python3
"""
Fix truthy values in Ansible YAML files.

Rewrites unquoted yes/no/on/off to true/false in key-value contexts while
preserving quoted strings and comments. Intended as a focused fixer split
from a larger all-in-one script.

Usage:
  - Fix specific files:    scripts/fix_truthy.py path1.yml path2.yaml
  - Fix a directory tree:  scripts/fix_truthy.py path/to/dir

By default, files are modified in place only when changes occur.
Exit code is 0 on success; non-zero on unexpected errors.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List, Tuple
import sys

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import split_code_and_comment, iter_yaml_files  # type: ignore


TRUTH_VALUES = {
    'yes': 'true', 'Yes': 'true', 'YES': 'true',
    'no': 'false', 'No': 'false', 'NO': 'false',
    'on': 'true', 'On': 'true', 'ON': 'true',
    'off': 'false', 'Off': 'false', 'OFF': 'false',
}


# split_code_and_comment now provided by shared module


def fix_truth_values_in_line(line: str) -> str:
    """Fix truth values (yes/no/on/off) in a single YAML line.

    - Skips full-line comments
    - Preserves quoted strings
    - Operates on typical key: value and key=value patterns
    """
    stripped = line.lstrip()
    if not stripped or stripped.startswith('#'):
        return line

    code, comment = split_code_and_comment(line)

    # Identify quoted spans within code to avoid replacements inside quotes
    quote_spans: List[Tuple[int, int]] = []
    in_quotes = False
    quote_char = ''
    start = -1
    for i, ch in enumerate(code):
        if ch in ('"', "'"):
            prev = code[i - 1] if i > 0 else ''
            if prev == '\\':
                continue
            if not in_quotes:
                in_quotes = True
                quote_char = ch
                start = i
            elif ch == quote_char:
                in_quotes = False
                quote_spans.append((start, i))

    def inside_quotes(idx: int) -> bool:
        for s, e in quote_spans:
            if s <= idx <= e:
                return True
        return False

    result = code
    # Replace only when value tokens appear after ':' or '='
    for old, new in TRUTH_VALUES.items():
        # Patterns anchored to ':' or '=' assignments; allow delimiters after value
        # Delimiters include whitespace, end, comma, closing brace/bracket
        patterns = [
            rf'(:\s*){re.escape(old)}(?=(\s|$|[,}}\]]))',  # key: yes
            rf'(=\s*){re.escape(old)}(?=(\s|$|[,}}\]]))',   # key=yes
        ]
        for pattern in patterns:
            for m in list(re.finditer(pattern, result)):
                s, e = m.span()
                # Skip if match begins inside quotes
                if inside_quotes(s):
                    continue
                # Replace token while preserving following delimiter via lookahead
                pre = result[:s]
                grp1 = m.group(1)
                result = pre + grp1 + new + result[e:]

    return result + comment


def iter_target_files(paths: Iterable[str]) -> Iterable[Path]:
    # Delegate to shared helper for consistency
    yield from iter_yaml_files(paths)


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)
    fixed = [fix_truth_values_in_line(ln) for ln in lines]
    new_content = '\n'.join(fixed)
    if new_content != original:
        path.write_text(new_content + ('\n' if original.endswith('\n') else ''), encoding='utf-8')
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description='Fix truthy values (yes/no/on/off -> true/false) in Ansible YAML files.')
    ap.add_argument('paths', nargs='+', help='Files or directories to process')
    args = ap.parse_args()

    changed = 0
    checked = 0
    for file in iter_target_files(args.paths):
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
