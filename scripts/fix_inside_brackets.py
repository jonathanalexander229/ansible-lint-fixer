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


def _split_outside_quotes(text: str, sep: str) -> List[str]:
    parts: List[str] = []
    cur: List[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            cur.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            cur.append(ch)
        elif ch == sep and not in_single and not in_double:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append(''.join(cur))
    return parts


def _normalize_flow_list_inner(inner: str) -> str:
    inner = inner.strip()
    if not inner:
        return ''
    items = [p.strip() for p in _split_outside_quotes(inner, ',')]
    return ', '.join(items)


def _normalize_flow_lists_outside_quotes(code: str) -> str:
    # Apply simple list normalization [ a , b ] -> [a, b] outside quotes only
    out: List[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == '[' and not in_single and not in_double:
            # find matching ']' on this line (no multiline lists here)
            j = i + 1
            depth = 1
            while j < len(code) and depth > 0:
                if code[j] == '"' or code[j] == "'":
                    # skip quoted content inside brackets
                    quote = code[j]
                    j += 1
                    while j < len(code) and code[j] != quote:
                        # allow escaped quotes inside double quotes
                        if quote == '"' and code[j] == '\\':
                            j += 2
                            continue
                        j += 1
                elif code[j] == '[':
                    depth += 1
                elif code[j] == ']':
                    depth -= 1
                j += 1
            # j is position after the closing ']' or end of string
            segment = code[i:j]
            m = re.match(r"\[([^\n\]]*)\]", segment)
            if m:
                normalized = '[' + _normalize_flow_list_inner(m.group(1)) + ']'
                out.append(normalized)
            else:
                out.append(segment)
            i = j
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def fix_line(line: str) -> str:
    code, comment = split_code_and_comment(line)
    if not code.strip() or code.lstrip().startswith('#'):
        return line

    # Normalize spacing inside Jinja delimiters
    code = _normalize_jinja_spacing(code)
    # Normalize spaces in simple inline lists outside quotes
    code = _normalize_flow_lists_outside_quotes(code)

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
