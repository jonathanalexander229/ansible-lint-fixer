#!/usr/bin/env python3
"""
Fix long variable definition lines by converting to folded scalars and wrapping.

Targets lines of the form:
  <indent><key>: <long string>

Rules (kept simple):
  - Only processes mapping entries (not list items starting with '-').
  - Skips keys commonly used for tasks/controls: name, when, tags, with_*
  - Converts value to folded scalar (>):
        key: >  # preserves inline comment
          long content wrapped to fit within max length

Usage:
  scripts/fix_line_length_vars.py [--max-length 120] FILE_OR_DIR [...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, split_code_and_comment  # type: ignore


SKIP_KEYS = (
    'name', 'when', 'tags',
)


def is_var_definition(code: str) -> Tuple[bool, str, str, str]:
    """Return (True, indent, key, value) if code is a var definition line."""
    m = re.match(r'^(\s*)([^\-\s][^:]*?):\s*(.+)$', code)
    if not m:
        return False, '', '', ''
    indent, key, value = m.groups()
    # skip common non-var keys
    key_l = key.strip().lower()
    if key_l in SKIP_KEYS or key_l.startswith('with_'):
        return False, '', '', ''
    return True, indent, key, value


def strip_outer_quotes(text: str) -> Tuple[str, bool]:
    if len(text) >= 2 and ((text[0] == '"' and text[-1] == '"') or (text[0] == "'" and text[-1] == "'")):
        return text[1:-1], True
    return text, False


def wrap_text(text: str, width: int) -> List[str]:
    if width <= 10:
        width = 10
    words = text.split()
    if not words:
        return ['']
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur += ' ' + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def fix_line(code: str, max_length: int) -> List[str] | None:
    ok, indent, key, value = is_var_definition(code)
    if not ok:
        return None
    if len(code) <= max_length:
        return None

    # remove outer quotes for cleaner folded scalar value
    val_text, _ = strip_outer_quotes(value)

    # build folded scalar with wrapping
    header = f"{indent}{key}: >"
    content_indent = indent + '  '
    avail = max_length - len(content_indent)
    wrapped = wrap_text(val_text, avail)
    return [header] + [f"{content_indent}{ln}" for ln in wrapped]


def fix_file(path: Path, max_length: int) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)

    changed = False
    out: List[str] = []
    for ln in lines:
        code, comment = split_code_and_comment(ln)
        replacement = fix_line(code, max_length)
        if replacement is None:
            out.append(ln)
        else:
            # attach any inline comment to the header line
            if comment:
                replacement[0] = replacement[0] + ' ' + comment.strip()
            out.extend(replacement)
            changed = True

    if not changed:
        return False

    new_content = '\n'.join(out)
    # preserve existing trailing newline
    if original.endswith('\n') and not new_content.endswith('\n'):
        new_content += '\n'
    path.write_text(new_content, encoding='utf-8')
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description='Wrap long variable definition lines using folded scalars.')
    ap.add_argument('--max-length', type=int, default=120, help='Maximum line length (default: 120)')
    ap.add_argument('paths', nargs='+', help='Files or directories to process')
    args = ap.parse_args()

    changed = 0
    checked = 0
    for file in iter_yaml_files(args.paths):
        checked += 1
        try:
            if fix_file(file, args.max_length):
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

