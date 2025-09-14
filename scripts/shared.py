"""Shared helpers for ansible-lint fixer scripts."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple


def iter_yaml_files(paths: Iterable[str]) -> Iterator[Path]:
    """Yield .yml/.yaml files from given files or directories (recursive)."""
    exts = {'.yml', '.yaml'}
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix.lower() in exts:
            yield path
        elif path.is_dir():
            for sub in path.rglob('*'):
                if sub.is_file() and sub.suffix.lower() in exts:
                    yield sub


def split_code_and_comment(line: str) -> Tuple[str, str]:
    """Split a line into (code, comment) at the first unquoted '#'."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            if i == 0 or line[i - 1] != '\\':
                in_single = not in_single
        elif ch == '"' and not in_single:
            if i == 0 or line[i - 1] != '\\':
                in_double = not in_double
        elif ch == '#' and not in_single and not in_double:
            return line[:i], line[i:]
    return line, ''


def first_non_empty_index(lines: List[str]) -> Optional[int]:
    for i, ln in enumerate(lines):
        if ln.strip():
            return i
    return None


def ensure_document_start(lines: List[str]) -> Tuple[List[str], bool]:
    """Ensure YAML document starts with '---' as the first non-empty line."""
    if not lines:
        return ['---'], True

    idx = first_non_empty_index(lines)
    if idx is None:
        # file is all empty lines; replace with just doc start
        return ['---'], True

    if lines[idx].strip() == '---':
        return lines, False

    # Insert '---' at the very top; keep a blank line after if there were leading empties
    out: List[str] = ['---']
    if idx > 0:
        out.append('')
    out.extend(lines)
    return out, True


def ensure_final_newline(text: str) -> Tuple[str, bool]:
    """Ensure text ends with a single newline."""
    if not text.endswith('\n'):
        return text + '\n', True
    return text, False


# Common module FQCN mappings used across fixers
FQCN_MAPPINGS = {
    'copy': 'ansible.builtin.copy',
    'file': 'ansible.builtin.file',
    'template': 'ansible.builtin.template',
    'service': 'ansible.builtin.service',
    'systemd': 'ansible.builtin.systemd',
    'user': 'ansible.builtin.user',
    'group': 'ansible.builtin.group',
    'package': 'ansible.builtin.package',
    'yum': 'ansible.builtin.yum',
    'apt': 'ansible.builtin.apt',
    'pip': 'ansible.builtin.pip',
    'git': 'ansible.builtin.git',
    'uri': 'ansible.builtin.uri',
    'get_url': 'ansible.builtin.get_url',
    'unarchive': 'ansible.builtin.unarchive',
    'lineinfile': 'ansible.builtin.lineinfile',
    'blockinfile': 'ansible.builtin.blockinfile',
    'replace': 'ansible.builtin.replace',
    'find': 'ansible.builtin.find',
    'stat': 'ansible.builtin.stat',
    'debug': 'ansible.builtin.debug',
    'fail': 'ansible.builtin.fail',
    'assert': 'ansible.builtin.assert',
    'set_fact': 'ansible.builtin.set_fact',
    'include_vars': 'ansible.builtin.include_vars',
    'command': 'ansible.builtin.command',
    'shell': 'ansible.builtin.shell',
    'raw': 'ansible.builtin.raw',
    'script': 'ansible.builtin.script',
    'cron': 'ansible.builtin.cron',
    'mount': 'ansible.builtin.mount',
    'sysctl': 'ansible.builtin.sysctl',
    'setup': 'ansible.builtin.setup',
    'ping': 'ansible.builtin.ping',
    'wait_for': 'ansible.builtin.wait_for',
    'pause': 'ansible.builtin.pause',
    'fetch': 'ansible.builtin.fetch',
    'synchronize': 'ansible.builtin.synchronize',
    'slurp': 'ansible.builtin.slurp',
    'include': 'ansible.builtin.include',
    'include_tasks': 'ansible.builtin.include_tasks',
    'import_tasks': 'ansible.builtin.import_tasks',
    'include_role': 'ansible.builtin.include_role',
    'import_role': 'ansible.builtin.import_role',
    # Builtin meta
    'meta': 'ansible.builtin.meta',
    # Common community actions seen in reports
    'redfish_command': 'community.general.redfish_command',
    'ipmi_power': 'community.general.ipmi_power',
    'ipmi_boot': 'community.general.ipmi_boot',
}
