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


def replace_fqcn_in_line(line: str) -> str:
    code, comment = split_code_and_comment(line)
    stripped = code.strip()
    if not stripped or stripped.startswith('#'):
        return line

    # Skip if already using a collection prefix on the module token
    # We'll simply not replace if the specific fqcn already appears on the line.
    for short, fqcn in FQCN_MAPPINGS.items():
        if fqcn in code:
            continue  # already fqcn for this module on this line

        # Match module usage patterns at the start of a mapping key
        # - "- copy:"  (task list item)
        # - "  copy:"  (indented mapping)
        # - "copy:"    (top-level key)
        patterns = [
            rf'^(\s*-\s*){re.escape(short)}:(\s|$)',
            rf'^(\s+){re.escape(short)}:(\s|$)',
            rf'^{re.escape(short)}:(\s|$)',
        ]

        for pat in patterns:
            m = re.search(pat, code)
            if m:
                # Rebuild with fqcn while preserving indentation and trailing whitespace
                start, end = m.span()
                prefix = code[:start]
                matched = code[start:end]
                replaced = matched.replace(f"{short}:", f"{fqcn}:")
                code = prefix + replaced + code[end:]
                break

    return code + comment


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)
    fixed = [replace_fqcn_in_line(ln) for ln in lines]
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

