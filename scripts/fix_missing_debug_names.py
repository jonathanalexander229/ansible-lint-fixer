#!/usr/bin/env python3
"""
Add task names only for debug tasks missing '- name:'

Transforms tasks like:
  - debug: msg=hello
  - debug:\n      msg: hello
into:
  - name: Debug
    ansible.builtin.debug:
      msg: hello

Scope:
- Only touches debug/ansible.builtin.debug tasks
- Works for tasks-only files or playbooks with tasks:
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, split_code_and_comment  # type: ignore


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=False)
    out: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        code, comment = split_code_and_comment(line)

        # Detect start of a task list item
        m_dash = re.match(r"^(?P<spaces>\s*)-\s+.*", code)
        if not m_dash:
            out.append(line)
            i += 1
            continue

        spaces = m_dash.group("spaces")
        dash_indent = len(spaces)
        task_key_indent = dash_indent + 2

        # Check if this task already has a name at task level in following sibling keys
        has_name = False
        j = i
        while j < len(lines):
            c2, _ = split_code_and_comment(lines[j])
            if j == i:
                pass
            else:
                # Stop when we hit a new list item at same or less indent
                if re.match(rf"^(\s){{0,{dash_indent}}}-\s+", c2):
                    break
                # Task-level sibling keys are exactly at task_key_indent
                if re.match(rf"^(\s){{{task_key_indent}}}name:\s*", c2):
                    has_name = True
                    break
            j += 1

        # If the task already has a name, just pass through original line
        # and regular processing
        if has_name:
            out.append(line)
            i += 1
            continue

        # Try to match debug module on this task line
        # 1) Free-form: - debug: msg=...
        m_free = re.match(
            r"^(?P<spaces>\s*)-\s+(?P<mod>(?:ansible\.builtin\.)?debug):\s*msg=(?P<val>[^#\n]+?)\s*$",
            code,
        )
        if m_free:
            val = m_free.group("val").rstrip()
            out.append(f"{spaces}- name: Debug")
            out.append(f"{spaces}  ansible.builtin.debug:{comment}")
            out.append(f"{spaces}    msg: {val}")
            i += 1
            continue

        # 2) Mapping header: - debug:
        m_map = re.match(
            r"^(?P<spaces>\s*)-\s+(?P<mod>(?:ansible\.builtin\.)?debug):\s*$",
            code,
        )
        if m_map:
            out.append(f"{spaces}- name: Debug")
            out.append(f"{spaces}  ansible.builtin.debug:{comment}")
            i += 1
            continue

        # Otherwise, leave the task untouched
        out.append(line)
        i += 1

    new_text = "\n".join(out)
    if original.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    if new_text != original:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Add - name: Debug to debug tasks missing a name.")
    ap.add_argument("paths", nargs="+", help="Files or directories to process")
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
        print("No YAML files found in provided paths.")
        return 1
    print(f"Summary: {changed} changed, {checked} checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

