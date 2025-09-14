#!/usr/bin/env python3
"""
Fix "too many spaces after colon" in YAML mappings.

Scope (kept simple and safe):
  - Compress multiple spaces after the first mapping colon on a line to a single space.
    Examples: "key:   value" -> "key: value", "- module:    param=val" -> "- module: param=val".
  - Normalize spaces after colons inside simple inline maps on the same line: { a:  1, b:  2 } -> { a: 1, b: 2 }.

Out of scope:
  - Colons inside quoted strings (left untouched).
  - URL schemes and other value colons are not altered beyond the mapping separator.

Usage:
  scripts/fix_colons.py FILE_OR_DIR [...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List

# Allow importing from the scripts directory when run directly
sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, split_code_and_comment, ensure_final_newline  # type: ignore


def compress_after_first_mapping_colon(code: str) -> str:
    """Compress multiple spaces after the first mapping colon on a line.

    Matches lines like:
      <indent>key:   value
      <indent>- module:    params
    and reduces the spaces after ':' to a single space.
    Skips lines that don't look like a mapping at line start.
    """
    m = re.match(r"^(\s*(-\s*)?[^:#\n][^:]*:)(\s{2,})(.*)$", code)
    if not m:
        return code
    prefix, _, _, rest = m.groups()
    return f"{prefix} {rest}"


def normalize_inline_map_colons(code: str) -> str:
    """Within simple one-line inline maps, compress spaces after ':' to a single space.
    Avoids touching quoted strings.
    """
    def repl(m: re.Match) -> str:
        inner = m.group(1)
        # Walk through inner, compressing spaces after ':' only when outside quotes
        out: List[str] = []
        in_single = False
        in_double = False
        i = 0
        while i < len(inner):
            ch = inner[i]
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
            if ch == ':' and not in_single and not in_double:
                out.append(':')
                # skip over spaces after ':' and leave one space if next non-space isn't '}' or ','
                j = i + 1
                k = j
                while k < len(inner) and inner[k] == ' ':
                    k += 1
                if k < len(inner) and inner[k] not in ['}', ',']:
                    out.append(' ')
                i = k
                continue
            out.append(ch)
            i += 1
        return '{' + ''.join(out).strip() + '}'

    # Simple inline map matcher (no nested braces)
    return re.sub(r"\{([^{}\n]*)\}", repl, code)


def fix_line(line: str) -> str:
    code, comment = split_code_and_comment(line)
    if not code.strip() or code.lstrip().startswith('#'):
        return line

    # First, compress after first mapping colon on the line
    code2 = compress_after_first_mapping_colon(code)
    # Then, normalize inline map colon spacing
    code3 = normalize_inline_map_colons(code2)

    return code3 + comment


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines(keepends=False)
    fixed_lines = [fix_line(ln) for ln in lines]
    new_content = '\n'.join(fixed_lines)
    new_content, _ = ensure_final_newline(new_content)
    if new_content != original:
        path.write_text(new_content, encoding='utf-8')
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description='Compress excessive spaces after mapping colons in YAML.')
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

