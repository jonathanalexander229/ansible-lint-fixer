#!/usr/bin/env python3
"""
Fix FQCN (Fully Qualified Collection Name) for Ansible modules.

Converts short module names (e.g., copy:, template:) to ansible.builtin.*
using a shared mapping. Skips lines already using a collection prefix and
preserves comments. Operates line-by-line conservatively.

Usage:
  scripts/fix_fqcn.py FILE_OR_DIR [...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, split_code_and_comment, FQCN_MAPPINGS  # type: ignore


def replace_fqcn_in_line_at_indent(code: str, target_indent: int) -> str:
    """Replace short module name with FQCN if key is at target indent.

    - Only replaces mapping keys exactly at target_indent columns.
    - Skips if the fqcn already appears in the code.
    - Returns modified code segment only (no comment portion).
    """
    # Determine current indent of this code segment
    leading = len(code) - len(code.lstrip(' '))
    if leading != target_indent:
        return code

    for short, fqcn in FQCN_MAPPINGS.items():
        if fqcn in code:
            continue
        # Key must begin right after indentation
        if re.match(rf'^(\s){{{target_indent}}}{re.escape(short)}:(\s|$)', code):
            return code.replace(f"{short}:", f"{fqcn}:", 1)
    return code


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)

    fixed: list[str] = []
    # Track the indentation level for keys within a task list item
    # When we see a list dash ("- "), keys of the mapping in that item typically
    # start at dash_indent + 2 spaces.
    dash_indent: int | None = None
    task_key_indent: int | None = None

    for line in lines:
        code, comment = split_code_and_comment(line)
        stripped = code.strip()

        # Detect start of a list item (task)
        m_dash = re.match(r'^(\s*)-\s+.*', code)
        if m_dash:
            dash_indent = len(m_dash.group(1))
            task_key_indent = dash_indent + 2

        # Try to replace when module appears right after the dash ("- copy:")
        replaced = False
        for short, fqcn in FQCN_MAPPINGS.items():
            if fqcn in code:
                continue
            m_mod_dash = re.search(rf'^(\s*-\s*){re.escape(short)}:(\s|$)', code)
            if m_mod_dash:
                start, end = m_mod_dash.span()
                prefix = code[:start]
                matched = code[start:end]
                code = prefix + matched.replace(f"{short}:", f"{fqcn}:") + code[end:]
                replaced = True
                break

        # If not replaced via dash form, attempt indent-based replacement
        if not replaced and task_key_indent is not None and stripped and not stripped.startswith('#'):
            code = replace_fqcn_in_line_at_indent(code, task_key_indent)

        fixed.append(code + comment)

    new_content = '\n'.join(fixed)
    if new_content != original:
        # preserve original final newline
        if original.endswith('\n') and not new_content.endswith('\n'):
            new_content += '\n'
        path.write_text(new_content, encoding='utf-8')
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description='Replace short Ansible modules with FQCN (ansible.builtin.*).')
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
