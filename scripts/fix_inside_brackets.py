#!/usr/bin/env python3
"""
Normalize spacing inside Jinja delimiters in YAML (Ansible style).

Rule:
  - Ensure exactly one space after opening and before closing braces:
      {{var}}      -> {{ var }}
      {{  expr  }} -> {{ expr }}
      {%block%}    -> {% block %}

Notes:
  - Only affects code (ignores comments) and leaves non-Jinja brackets alone.
  - Does not alter quoting or other content aside from trimming/spacing at delimiter edges.

Usage:
  scripts/fix_inside_brackets.py FILE_OR_DIR [...]
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


def _normalize_jinja_spacing(code: str) -> str:
    # Variables: {{ ... }}
    code = re.sub(r"\{\{\s*(.*?)\s*\}\}", lambda m: "{{ " + m.group(1).strip() + " }}", code)
    # Blocks: {% ... %}
    code = re.sub(r"\{\%\s*(.*?)\s*\%\}", lambda m: "{% " + m.group(1).strip() + " %}", code)
    return code


def fix_line(line: str) -> str:
    code, comment = split_code_and_comment(line)
    if not code.strip() or code.lstrip().startswith('#'):
        return line

    # Normalize spacing inside Jinja delimiters only
    code = _normalize_jinja_spacing(code)

    return code + comment


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)
    fixed_lines = [fix_line(ln) for ln in lines]
    new_content = '\n'.join(fixed_lines)
    if original.endswith('\n') and not new_content.endswith('\n'):
        new_content += '\n'
    if new_content != original:
        path.write_text(new_content, encoding='utf-8')
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description='Normalize spaces inside inline brackets/braces in YAML flow collections.')
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
