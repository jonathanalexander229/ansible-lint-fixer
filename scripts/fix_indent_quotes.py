#!/usr/bin/env python3
"""
Fix indentation and simple quote issues in YAML files.

Indentation:
  - Converts leading tabs to spaces.
  - Normalizes indentation to multiples of --indent-size (default 2).

Quotes:
  - Unquotes when: expressions like "...{{ var }}..." -> when: ...{{ var }}...
  - Keeps parameter values like param: "{{ var }}" quoted (do not unquote).
  - Unquotes simple booleans/numbers after ':' like ": "true"" -> ": true"

Usage:
  scripts/fix_indent_quotes.py [--indent-size N] FILE_OR_DIR [...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, split_code_and_comment  # type: ignore


def fix_indentation(line: str, indent_size: int) -> str:
    if not line or line == "\n":
        return line

    # Extract leading whitespace run
    i = 0
    while i < len(line) and line[i] in (' ', '\t'):
        i += 1
    leading = line[:i]
    rest = line[i:]

    # Expand tabs to spaces strictly in the leading whitespace
    if indent_size <= 0:
        indent_size = 2
    spaces = 0
    for ch in leading:
        spaces += indent_size if ch == '\t' else 1

    # Make indentation a multiple of indent_size by flooring (conservative)
    # This avoids increasing indentation depth which may change YAML structure.
    corrected = (spaces // indent_size) * indent_size

    return (' ' * corrected) + rest


def fix_quotes(line: str) -> str:
    code, comment = split_code_and_comment(line)
    if code.lstrip().startswith('#'):
        return line  # keep full-line comments unchanged

    # 1) Unquote when: "...{{ ... }}..."
    code = re.sub(r'when:\s*"([^"]*\{\{[^}]*\}\}[^"]*)"', r'when: \1', code)

    # 2) Unquote simple booleans/numbers after ':'
    code = re.sub(r':\s*"(true|false|\d+)"', r': \1', code)

    # 3) Normalize quoting style for scalar values after ':' when safe
    code = normalize_scalar_quotes(code)

    return code + comment


def parse_key_value_line(code: str) -> Optional[Tuple[str, str, str]]:
    """Parse '<indent><key>: <value>' lines; return (indent, key, value)."""
    m = re.match(r'^(\s*)([^\-\s][^:]*?):\s*(.+)$', code)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def needs_quotes(val: str) -> bool:
    if not val:
        return False
    if val.startswith(('>', '|')):
        return False
    # Unquoted booleans/numbers handled elsewhere; keep as-is
    if re.fullmatch(r'(true|false|\d+)', val):
        return False
    # Require quotes if contains colon-space, starts with flow chars, or Jinja templating
    if ': ' in val or val[0] in '{[' or '{{' in val or '{%' in val or '%}' in val or '}}' in val:
        return True
    # Leading/trailing spaces
    if val != val.strip():
        return True
    # Spaces are fine unquoted in YAML, but we keep simple and leave unquoted unless special
    return False


def unwrap(val: str) -> Tuple[str, Optional[str]]:
    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
        return val[1:-1], val[0]
    return val, None


def quote_with(val: str, quote: str) -> str:
    if quote == "'":
        return "'" + val.replace("'", "''") + "'"
    else:
        return '"' + val.replace('"', '\\"') + '"'


def choose_quote(val: str) -> str:
    # Prefer double quotes for templated or complex strings
    if '{{' in val or '{%' in val or '}}' in val or '%}' in val:
        return '"'
    if "'" in val and '"' not in val:
        return '"'
    if '"' in val and "'" not in val:
        return "'"
    # Contains both or neither: default to double quotes
    return '"'


def normalize_scalar_quotes(code: str) -> str:
    parsed = parse_key_value_line(code)
    if not parsed:
        return code
    indent, key, value = parsed

    # Skip module shorthand params like "name=vim state=present" to avoid altering
    if '=' in value and not (value.startswith('"') or value.startswith("'")):
        return code

    inner, existing = unwrap(value)

    # If value looks like boolean/number and was quoted, leave unquoting to earlier rule
    if re.fullmatch(r'(true|false|\d+)', inner):
        return code

    # Decide if we should quote or leave unquoted
    force_double = key.strip() == 'name'
    if force_double:
        new_val = quote_with(inner, '"')
    else:
        if needs_quotes(inner):
            q = choose_quote(inner)
            new_val = quote_with(inner, q)
        else:
            # Leave as-is if already unquoted; if previously quoted but not required, we can drop quotes
            new_val = inner

    return f"{indent}{key}: {new_val}"


def left_align_top_level_list(lines: List[str]) -> List[str]:
    # Find first meaningful line (not empty/comment); skip '---'
    idx = 0
    while idx < len(lines):
        s = lines[idx].strip()
        if not s or s.startswith('#'):
            idx += 1
            continue
        if s == '---':
            idx += 1
            continue
        break
    if idx >= len(lines):
        return lines
    line = lines[idx]
    lstripped = line.lstrip(' ')
    if not lstripped.startswith('- '):
        return lines
    # Count spaces to dash
    to_remove = len(line) - len(lstripped)
    if to_remove <= 0:
        return lines
    out: List[str] = []
    for ln in lines:
        # Remove up to to_remove spaces from the start if present
        k = 0
        while k < len(ln) and k < to_remove and ln[k] == ' ':
            k += 1
        out.append(ln[k:])
    return out


def fix_file(path: Path, indent_size: int) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)

    # First pass: normalize leading whitespace and quotes per line
    first_pass: List[str] = []
    for ln in lines:
        ln2 = fix_indentation(ln, indent_size)
        ln3 = fix_quotes(ln2)
        first_pass.append(ln3)

    # Pass 1.5: if the first non-comment, non-empty, non-docstart line is an indented list item,
    # left-align that top-level list by removing its leading spaces from the whole block.
    first_pass = left_align_top_level_list(first_pass)

    # Second pass: context-aware indentation for task child keys
    fixed_lines: List[str] = []
    in_task = False
    base_indent = 0
    shift_active = False
    shift_threshold = 0
    shift_amount = indent_size

    def count_spaces_prefix(s: str) -> int:
        i = 0
        while i < len(s) and s[i] == ' ':
            i += 1
        return i

    for ln in first_pass:
        stripped = ln.lstrip(' ')
        indent = count_spaces_prefix(ln)

        # Detect list item task start
        if stripped.startswith('- '):
            in_task = True
            base_indent = indent
            shift_active = False  # reset any pending shift
            fixed_lines.append(ln)
            continue

        # Determine if we left the task block
        if in_task:
            if not stripped:
                fixed_lines.append(ln)
                continue
            # End task context only when dedenting below base, or a new list item at base indent
            if indent < base_indent or (indent == base_indent and stripped.startswith('- ')):
                in_task = False
                shift_active = False
                # fall through to default handling

        if in_task:
            # If a child mapping key is aligned with the task dash level, bump it one indent level
            # We detect a mapping by the presence of ':' and not starting another list item
            if indent == base_indent and ':' in stripped and not stripped.startswith('- '):
                new_indent = base_indent + indent_size
                ln = (' ' * new_indent) + stripped
                # If the key is 'vars:', shift following nested lines by one indent level
                if stripped.startswith('vars:'):
                    shift_active = True
                    shift_threshold = new_indent

        # Apply pending shift for nested block under vars:
        if shift_active and not stripped.startswith('#'):
            if indent >= shift_threshold:
                ln = (' ' * (indent + shift_amount)) + stripped
            else:
                # We've left the vars block
                shift_active = False

        fixed_lines.append(ln)

    # Third pass: specifically ensure nested lines under 'vars:' are indented one level deeper
    final_lines: List[str] = fixed_lines[:]
    i = 0
    while i < len(final_lines):
        line = final_lines[i]
        stripped = line.lstrip(' ')
        if stripped.startswith('vars:'):
            # Determine vars indent
            vars_indent = len(line) - len(stripped)
            j = i + 1
            while j < len(final_lines):
                ln = final_lines[j]
                s = ln.lstrip(' ')
                if not s:
                    j += 1
                    continue
                cur_indent = len(ln) - len(s)
                if cur_indent < vars_indent:
                    break
                if cur_indent == vars_indent:
                    final_lines[j] = (' ' * (cur_indent + indent_size)) + s
                j += 1
            # continue scanning after vars block
            i += 1
            continue
        i += 1

    new_content = '\n'.join(final_lines)
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
