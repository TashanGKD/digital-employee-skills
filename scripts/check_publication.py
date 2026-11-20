#!/usr/bin/env python3
"""Reject private identities, broken/escaping links and unsealed public payloads.

Read-only, stdlib-only, no network. The manifest covers this checker and tests.
This verifies the distribution, never live employees, WeChat or delivery.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import unquote

SKILLS = ('digital-employee', 'codex-thread-handoff', 'wechat-aup-control',
          'wechat-write', 'wechat-local-read', 'notebook-secretary')
TEXT = {'.md', '.py', '.mjs', '.json', '.yaml', '.yml', '.sh', '.svg'}
PRIVATE = re.compile(r'(?:wxid_[A-Za-z0-9_-]+|\b[0-9]{8,}@chatroom|'
                     r'01a[0-9a-f]{5}-[0-9a-f-]{27,}|'
                     r'/Users/[A-Za-z0-9_-]+/|/home/[A-Za-z0-9_-]+/|'
                     r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]+|'
                     r'-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|'
                     r'https?://[^/\s:]+:[^/\s]+@)')


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate manifest key')
        result[key] = value
    return result


def payload(root):
    result = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__')]
        for n in dirs + names:
            if (Path(base) / n).is_symlink():
                raise ValueError('symlink payload refused')
        for n in names:
            p = Path(base) / n
            if p.suffix == '.pyc':
                continue
            if not p.is_file() or p.stat().st_size > 20 * 1024 * 1024:
                raise ValueError('ordinary bounded file required')
            rel = p.relative_to(root).as_posix()
            if rel != 'MANIFEST.json':
                result.append(rel)
    return sorted(result)


def check(root):
    root = Path(root)
    if not root.is_absolute() or '..' in root.parts or not root.is_dir():
        raise ValueError('normalized absolute repository root required')
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('symlink root refused')
    files = payload(root)
    if (root / 'MANIFEST.json').is_symlink():
        raise ValueError('symlink manifest refused')
    manifest = json.loads((root / 'MANIFEST.json').read_text(), object_pairs_hook=unique_pairs)
    expected = manifest.get('files')
    if not isinstance(expected, dict):
        raise ValueError('manifest files required')
    for name, digest in expected.items():
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or p.as_posix() != name or '\\' in name:
            raise ValueError('unsafe manifest path')
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('manifest hash required')
    if set(files) != set(expected):
        raise ValueError('manifest file set differs')
    for rel in files:
        p = root / rel
        if hashlib.sha256(p.read_bytes()).hexdigest() != expected[rel]:
            raise ValueError('manifest hash differs: ' + rel)
        if p.suffix in TEXT:
            text = p.read_text()
            if PRIVATE.search(text):
                raise ValueError('private identity or credential pattern: ' + rel)
            if p.suffix == '.md':
                for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text):
                    target = unquote(target.split('#', 1)[0])
                    if not target or re.match(r'^[a-z][a-z0-9+.-]*:', target):
                        continue
                    resolved = (p.parent / target).resolve()
                    if root not in resolved.parents or not resolved.is_file():
                        raise ValueError('broken or escaping link: ' + rel + ' -> ' + target)
    actual = sorted(p.name for p in (root / 'skills').iterdir() if p.is_dir())
    if actual != sorted(SKILLS):
        raise ValueError('skill folder set differs')
    for name in SKILLS:
        text = (root / 'skills' / name / 'SKILL.md').read_text()
        if not text.startswith('---\n') or text.count('\n---\n') < 1:
            raise ValueError('skill frontmatter required: ' + name)
        header = text.split('---', 2)[1]
        if not re.search(r'^name: ' + re.escape(name) + r'\s*$', header, re.M):
            raise ValueError('skill name mismatch: ' + name)
        if not re.search(r'^description: .+', header, re.M):
            raise ValueError('skill description required: ' + name)
        if not (root / 'skills' / name / 'README.md').is_file():
            raise ValueError('skill README required: ' + name)
    for required in ('README.md', 'LICENSE', 'scripts/check_publication.py'):
        if required not in expected:
            raise ValueError('required file not sealed: ' + required)
    return {'skills': len(SKILLS), 'files': len(files), 'state': 'passed',
            'scope': 'public package only; no live-system acceptance'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    try:
        print(json.dumps(check(args.root)))
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'state': 'failed', 'reason': str(exc)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
