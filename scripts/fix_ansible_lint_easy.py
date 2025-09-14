#!/usr/bin/env python3
"""
Fix a subset of easy ansible-lint issues:
- name[casing]: Capitalize first letter in task/handler names
- name[missing]: Add a basic name when missing in a task item
- no-free-form (debug): Convert inline `debug: msg=...` to mapping style
- fqcn[action]/fqcn[action-core]: Use FQCN for module actions via shared mappings

Usage:
  scripts/fix_ansible_lint_easy.py FILE_OR_DIR [...]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from shared import iter_yaml_files, split_code_and_comment, FQCN_MAPPINGS  # type: ignore


def capitalize_first_alpha(s: str) -> str:
    for i, ch in enumerate(s):
        if ch.isalpha():
            if ch.islower():
                return s[:i] + ch.upper() + s[i + 1 :]
            break
    return s


def fix_name_casing_in_line(line: str) -> str:
    code, comment = split_code_and_comment(line)
    m = re.match(r"^(\s*-?\s*)name:\s*(.+?)\s*$", code)
    if not m:
        return line
    prefix, value = m.groups()
    # Don't change empty or templated-only names
    if not value or value.strip().startswith("{{"):
        return line
    fixed = capitalize_first_alpha(value)
    return f"{prefix}name: {fixed}{comment}"


def rewrite_name_template_placement(line: str) -> str:
    """Move any Jinja templates inside name to the end of the string.

    Example: "Verify {{ ver }} is {{ ok }} now" -> "Verify is now {{ ver }} {{ ok }}".
    Leaves names that already end with only Jinja unchanged. Operates on single-line names.
    """
    code, comment = split_code_and_comment(line)
    m = re.match(r"^(?P<prefix>\s*-?\s*name:\s*)(?P<value>.+?)\s*$", code)
    if not m:
        return line
    prefix = m.group("prefix")
    value = m.group("value")

    # Find all jinja occurrences and remove them from their positions
    jinja_re = re.compile(r"\{\{[^}]*\}\}")
    found = jinja_re.findall(value)
    if not found:
        return line
    # If value already ends with only jinja (possibly multiple) separated by spaces, skip
    tail = value.rstrip()
    # strip trailing jinja blocks from end
    tail_without_trailing = jinja_re.sub("", tail)
    if tail_without_trailing.strip() == "":
        # name value is only jinja (or ends with only jinja after spaces)
        return line

    # Remove all jinja from the value and collapse spaces
    value_no_jinja = jinja_re.sub("", value)
    value_no_jinja = re.sub(r"\s+", " ", value_no_jinja).strip()
    jinj = " ".join(found).strip()
    if value_no_jinja:
        new_val = f"{value_no_jinja} {jinj}".strip()
    else:
        new_val = jinj
    return f"{prefix}{new_val}{comment}"


def convert_debug_free_form(line: str) -> list[str] | None:
    code, comment = split_code_and_comment(line)
    # Match various forms: optional dash, module token, then free-form msg=
    m = re.match(r"^(?P<spaces>\s*)(?P<dash>-\s+)?(?P<mod>(?:ansible\.builtin\.)?debug):\s*msg=(?P<val>[^#\n]+?)\s*$",
                 code)
    if not m:
        return None
    spaces = m.group("spaces") or ""
    dash = m.group("dash") or ""
    # Always normalize to builtin FQCN for debug
    mod = "ansible.builtin.debug"
    val = m.group("val").rstrip()
    param_indent = spaces + "  "
    return [f"{spaces}{dash}{mod}:{comment}", f"{param_indent}msg: {val}"]


def replace_fqcn_module_token(code: str) -> str:
    # dash-line module key: - module:
    for short, fqcn in FQCN_MAPPINGS.items():
        if fqcn in code:
            continue
        m = re.search(rf"^(\s*-\s*){re.escape(short)}:(\s|$)", code)
        if m:
            start, end = m.span()
            prefix = code[:start]
            matched = code[start:end]
            return prefix + matched.replace(f"{short}:", f"{fqcn}:") + code[end:]
    return code


def replace_fqcn_module_at_indent(code: str, target_indent: int) -> str:
    lead = len(code) - len(code.lstrip(" "))
    if lead != target_indent:
        return code
    for short, fqcn in FQCN_MAPPINGS.items():
        if fqcn in code:
            continue
        if re.match(rf"^(\s){{{target_indent}}}{re.escape(short)}:(\s|$)", code):
            return code.replace(f"{short}:", f"{fqcn}:", 1)
    return code


def is_read_only_command(cmd: str) -> bool:
    """Heuristic: returns True if the shell/command looks read-only.
    Conservative: disqualify on redirects, in-place edits, or known mutators.
    """
    lc = cmd.strip()
    # Disqualify if any obvious mutating patterns
    mutators = [
        ">>", ">", "| tee", " tee ", "sed -i", "chmod", "chown", "mkdir", "rmdir", "rm ", "mv ", "cp ",
        "truncate", "dd ", "ln ", "systemctl", "service ", "supervisorctl", "touch ", "usermod", "useradd",
        "groupadd", "modprobe", "yum ", "apt ", "dnf ", "pip ", "git ", "curl -o", "wget -O",
    ]
    for m in mutators:
        if m in lc:
            return False
    # Allow-list of common read-only starters
    starters = [
        "cat", "grep", "egrep", "zgrep", "head", "tail", "awk", "sed ", "stat", "test ", "[ ", "true",
        "false", "id", "uname", "which", "command -v", "hostname", "date", "whoami", "uptime", "sysctl -n",
        "ls ", "find ", "echo ",
    ]
    for s in starters:
        if lc.startswith(s):
            # sed allowed only without -i and no redirection; already filtered
            return True
    return False


def convert_shell_command_free_form_add_changed_when(line: str) -> list[str] | None:
    """If line is free-form shell/command and read-only, convert to mapping and add changed_when: false."""
    code, comment = split_code_and_comment(line)
    m = re.match(r"^(?P<spaces>\s*)(?P<dash>-\s+)?(?P<mod>(?:ansible\.builtin\.)?(?:shell|command)):\s*(?P<val>[^#\n]+?)\s*$",
                 code)
    if not m:
        return None
    spaces = m.group("spaces") or ""
    dash = m.group("dash") or ""
    mod = m.group("mod")
    val = m.group("val").rstrip()
    if not is_read_only_command(val):
        return None
    param_indent = spaces + "  "
    return [f"{spaces}{dash}{mod}:{comment}", f"{param_indent}cmd: {val}", f"{param_indent}changed_when: false"]


def add_missing_name_after_module(code: str, name_seen: bool, in_tasks: bool) -> tuple[str, list[str] | None]:
    # If no name seen yet and we hit a module key after dash or at task indent, add a name
    # Detect the module token and derive a simple name like "<Module> task"
    # dash form
    m = re.match(r"^(\s*-\s*)([\w.]+):(\s|$)", code)
    if m and in_tasks and not name_seen:
        dash_prefix = m.group(1)  # includes leading spaces + '- '
        m2 = re.match(r"^(\s*)-\s*$", dash_prefix)
        base = m2.group(1) if m2 else ""
        param_indent = base + "  "
        module = m.group(2).split(".")[-1]
        title = module.replace("_", " ").title()
        return code, [f"{param_indent}name: {title}"]

    return code, None


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=False)
    out: list[str] = []

    dash_indent: int | None = None
    task_key_indent: int | None = None
    in_tasks: bool = False
    tasks_indent: int | None = None
    name_seen: bool = False

    for i, line in enumerate(lines):
        code, comment = split_code_and_comment(line)
        stripped = code.strip()

        # Track entering/leaving tasks section
        line_indent = len(code) - len(code.lstrip(' '))
        if re.match(r"^\s*tasks:\s*$", code):
            in_tasks = True
            tasks_indent = line_indent
        elif in_tasks and tasks_indent is not None and stripped and line_indent <= tasks_indent and not code.startswith(' ' * (tasks_indent + 1)):
            # Dedented out of tasks section
            in_tasks = False
            tasks_indent = None

        # Track task item context
        m_dash = re.match(r"^(\s*)-\s+.*", code)
        if m_dash:
            dash_indent = len(m_dash.group(1))
            task_key_indent = (dash_indent or 0) + 2
            name_seen = False

        # If this is any name: line within a task, mark seen (even if no change needed)
        if in_tasks and re.match(r"^\s*-?\s*name:\s*", code):
            name_seen = True

        # Fix debug free-form first (returns multiple lines if changed)
        multi = convert_debug_free_form(line)
        if multi:
            out.extend(multi)
            # ensure name still tracked
            continue

        # Convert free-form shell/command when clearly read-only and add changed_when
        multi_sc = convert_shell_command_free_form_add_changed_when(line)
        if multi_sc:
            out.extend(multi_sc)
            continue

        # FQCN replacements only at module token positions
        before = code
        code = replace_fqcn_module_token(code)
        if code == before and task_key_indent is not None and stripped and not stripped.startswith("#"):
            code = replace_fqcn_module_at_indent(code, task_key_indent)

        # Add missing name if we see first module key in a task and haven't seen name yet
        code_after_name, inject = add_missing_name_after_module(code, name_seen, in_tasks)
        code = code_after_name
        if inject:
            out.append(code + comment)
            out.extend(inject)
            # mark name as present now
            name_seen = True
            continue

        # Move Jinja to end in name, then apply casing
        name_rewritten = rewrite_name_template_placement(code + comment)
        fixed_line = fix_name_casing_in_line(name_rewritten)
        if fixed_line != code + comment:
            name_seen = True
            out.append(fixed_line)
            continue

        # Pass through
        out.append(code + comment)

    new = "\n".join(out)
    if original.endswith("\n") and not new.endswith("\n"):
        new += "\n"
    if new != original:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Fix easy ansible-lint issues: name casing/missing, debug free-form, FQCN actions.")
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
