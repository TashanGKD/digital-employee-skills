#!/usr/bin/env python3
"""Check or regenerate one employee's CURRENT.md from its work notes. Stdlib only."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote

START = '<!-- employee-work:start -->'
END = '<!-- employee-work:end -->'
GENERATED = '<!-- digital-employee-current:v1 -->'
FIELDS = ('事情', '怎么来的', '这次想做到什么', '我的想法', '现在怎么样', '下一步', '时间', '过程笔记')
STATES = ('待推进', '等反馈', '先放放', '已办好', '不做了')


def ordinary(path, directory=False):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('symbolic link refused: ' + str(part))
    if directory and not path.is_dir():
        raise ValueError('existing work directory required: ' + str(path))
    if not directory and (not path.is_file() or path.stat().st_size > 1_000_000):
        raise ValueError('ordinary bounded note required: ' + path.name)


def collect(root):
    ordinary(root, directory=True)
    if root in (Path('/'), Path.home()):
        raise ValueError('choose the specific employee directory')
    folder = root / 'workbook'
    ordinary(folder, directory=True)
    rows, snapshots, titles = [], {}, set()
    paths = sorted(folder.glob('*.md'))
    if not paths:
        raise ValueError('no work notes; create actual notes before refreshing')
    for path in paths:
        ordinary(path)
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
            raise ValueError('one current-summary block required: ' + path.name)
        block = text.split(START, 1)[1].split(END, 1)[0]
        pairs = re.findall(r'^- \*\*([^*]+)\*\*：(.+)$', block, re.M)
        if tuple(k for k, _ in pairs) != FIELDS:
            raise ValueError('eight current fields required in documented order: ' + path.name)
        row = dict(pairs)
        if row['现在怎么样'] not in STATES or any(not x.strip() for x in row.values()):
            raise ValueError('nonempty fields and known state required: ' + path.name)
        if row['事情'] in titles:
            raise ValueError('distinct result titles required: ' + path.name)
        if row['现在怎么样'] == '等反馈' and not re.search(r'等|待|反馈|确认|提供|恢复|条件', row['下一步'] + row['时间']):
            raise ValueError('waiting must explain missing result/condition: ' + path.name)
        titles.add(row['事情'])
        row['file'] = path.name
        rows.append(row)
        snapshots[path] = hashlib.sha256(raw).hexdigest()
    return rows, snapshots


def cell(text):
    return text.replace('|', '\\|')


def render(rows):
    result = [GENERATED, '# 我自己的工作本', '',
              '从逐件笔记的当前摘要生成；改进展请改原笔记，再刷新本页。',
              '这里记录本岗位的责任和判断，共享业务事实仍按原真源。已办好只指本轮约定结果。', '']
    for state in STATES:
        subset = [r for r in rows if r['现在怎么样'] == state]
        result += ['## ' + state + ' · ' + str(len(subset)), '']
        if not subset:
            result += ['当前没有记录。', '']
            continue
        result += ['| 事情 | 本轮想得到的结果 | 我接下来怎么做 | 何时再看 |',
                   '|---|---|---|---|']
        for row in subset:
            label = cell(row['事情']).replace('[', '\\[').replace(']', '\\]')
            link = '[{}](workbook/{})'.format(label, quote(row['file']))
            result.append('| ' + ' | '.join([link, cell(row['这次想做到什么']), cell(row['下一步']), cell(row['时间'])]) + ' |')
        result.append('')
    result += ['本页只证明已记录工作的当前视图；不证明所有来源已读、业务事实正确或协作者已接受。', '']
    return '\n'.join(result)


def stable(root, snapshots):
    if set((root / 'workbook').glob('*.md')) != set(snapshots):
        raise ValueError('note set changed during refresh; reread before retry')
    for path, digest in snapshots.items():
        ordinary(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('note changed during refresh: ' + path.name)


def operate(root, action, execute):
    root = Path(root).absolute()
    rows, snapshots = collect(root)
    target = root / 'CURRENT.md'
    before = None
    if target.exists() or target.is_symlink():
        ordinary(target)
        before = target.read_bytes()
        if not before.decode('utf-8').startswith(GENERATED):
            raise ValueError('existing CURRENT is not owned by this generator; preserve and adapt it')
    content = render(rows).encode('utf-8')
    stable(root, snapshots)
    if action == 'check':
        if before != content:
            raise ValueError('CURRENT is missing or differs from current notes')
    elif execute:
        fd, temporary = tempfile.mkstemp(prefix='.CURRENT-', dir=root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            stable(root, snapshots)
            if (target.read_bytes() if target.exists() else None) != before:
                raise ValueError('CURRENT changed by another writer; no replacement performed')
            os.replace(temporary, target)
            # Detect a concurrent note change rather than declaring a stale view valid.
            stable(root, snapshots)
            if target.read_bytes() != content:
                raise ValueError('CURRENT changed after write; reread it')
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {'notes': len(rows), 'states': dict(Counter(r['现在怎么样'] for r in rows)),
            'action': action, 'written': action == 'refresh' and execute,
            'consistent': before == content if not (action == 'refresh' and execute) else True,
            'scope': 'local work-note/index structure; not business truth or scheduler verification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'refresh'], nargs='?')
    parser.add_argument('--root', help='explicit absolute employee directory; no default target')
    parser.add_argument('--execute', action='store_true', help='write only generated CURRENT.md')
    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        return
    if not args.root or not Path(args.root).is_absolute():
        parser.error('--root must name the absolute employee directory')
    try:
        print(json.dumps(operate(args.root, args.action, args.execute), ensure_ascii=False))
    except (ValueError, OSError, UnicodeError) as exc:
        print(json.dumps({'state': 'error', 'reason': str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == '__main__':
    main()
