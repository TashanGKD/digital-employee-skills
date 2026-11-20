#!/usr/bin/env python3
"""Small loopback-only client for the local v4 notebook contract.

No arguments: help only. Writes: offline preview unless --apply. No credentials
on disk, environment proxies, redirects, human confirmation, or automatic retries.
"""
import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

MAX_INPUT = 256 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,120}\Z')
AI = {'name': 'AI秘书', 'kind': 'ai'}
TASK_FIELDS = {'title', 'kind', 'domain', 'state', 'assignee', 'counterparty',
               'summary', 'proposedAt', 'timeRequirement', 'planDate', 'reviewDate',
               'condition', 'relatedRecordIds', 'completionCriterion',
               'recommendation', 'sources', 'needsReview', 'sourceTime', 'note',
               'requestId', 'actor'}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def parse_json(raw, maximum=MAX_INPUT):
    if len(raw.encode('utf-8') if isinstance(raw, str) else raw) > maximum:
        raise ValueError('JSON exceeds bounded size')
    def invalid(_):
        raise ValueError('JSON numbers must be finite')
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('invalid or overly nested JSON') from exc


def _id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('invalid stable identifier')
    return value


class ApiError(RuntimeError):
    def __init__(self, status):
        self.status = status
        message = {409: 'Revision conflict: re-read task and human history; re-plan before retry.',
                   400: 'Server rejected fields; check the current public contract.',
                   403: 'Origin/CSRF rejected; re-open client and verify live server.',
                   404: 'Task or route not found.'}.get(status, 'Notebook HTTP request failed.')
        super().__init__('HTTP ' + str(status) + ': ' + message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class Client:
    def __init__(self, base='http://127.0.0.1:8876'):
        if not isinstance(base, str) or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', base):
            raise ValueError('explicit numeric loopback HTTP origin required, without path/query')
        if not 1 <= int(base.rsplit(':', 1)[1]) <= 65535:
            raise ValueError('invalid loopback port')
        self.base = base
        self.token = None
        self.version = None
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _request(self, path, body=None):
        headers = {'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(data) > MAX_INPUT:
                raise ValueError('request exceeds 256 KiB')
            headers.update({'Content-Type': 'application/json', 'Origin': self.base,
                            'X-CSRF-Token': self.token})
        req = Request(self.base + path, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError('response exceeds 16 MiB; use bounded detail calls')
                return parse_json(raw, MAX_RESPONSE)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise ApiError(status) from None
        except URLError:
            raise RuntimeError('Local notebook unavailable; do not start a different/default database.') from None

    def get(self, operation, task_id=None):
        paths = {'health': '/api/health', 'bootstrap': '/api/bootstrap',
                 'messages': '/api/messages', 'sources': '/api/sources', 'jobs': '/api/jobs'}
        if operation == 'detail':
            path = '/api/tasks/' + _id(task_id)
        elif operation in paths and task_id is None:
            path = paths[operation]
        else:
            raise ValueError('unsupported read operation')
        result = self._request(path)
        if operation == 'bootstrap':
            self.token = result.pop('csrfToken', None)
            self.version = result.get('version')
        return result

    def write(self, operation, body, task_id=None, *, apply=False):
        if operation not in ('create', 'record', 'append') or not isinstance(body, dict):
            raise ValueError('only create, record, append are secretary write operations')
        allowed = ({'text', 'objectIds', 'attachments', 'sourceRefs', 'requestId', 'actor'}
                   if operation == 'append' else TASK_FIELDS | ({'expectedRevision'} if operation == 'record' else set()))
        if set(body) - allowed:
            raise ValueError('unknown/forbidden fields; human confirm is never a secretary action')
        if body.get('actor', AI) != AI or body.get('needsReview') is False:
            raise ValueError('cannot impersonate human acknowledgement')
        _id(body.get('requestId'))
        if operation == 'record':
            _id(task_id)
            if type(body.get('expectedRevision')) is not int or body['expectedRevision'] < 0:
                raise ValueError('record requires the revision actually read')
        elif task_id is not None:
            raise ValueError('task ID only belongs to record')
        body = dict(body, actor=dict(AI))
        # Validate bounded finite JSON before any network call, including preview.
        try:
            parse_json(json.dumps(body, ensure_ascii=False, allow_nan=False))
        except (RecursionError, UnicodeError) as exc:
            raise ValueError('invalid JSON request') from exc
        path = {'create': '/api/tasks', 'append': '/api/messages',
                'record': '/api/tasks/' + (task_id or '') + '/record'}[operation]
        if not apply:
            return {'preview': True, 'path': path, 'body': body}
        if not self.token:
            self.get('bootstrap')
            if not self.token:
                raise ValueError('bootstrap did not return a CSRF token')
        if not str(self.version or '').startswith('4.local.'):
            raise ValueError('unverified notebook version; inspect contract before writing')
        return self._request(path, body)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', default='http://127.0.0.1:8876')
    commands = p.add_subparsers(dest='command')
    for action in ('health', 'bootstrap', 'messages', 'sources', 'jobs'):
        commands.add_parser(action)
    detail = commands.add_parser('detail'); detail.add_argument('task_id')
    for action in ('create', 'record', 'append'):
        sub = commands.add_parser(action, help='JSON object on stdin; preview unless --apply')
        if action == 'record': sub.add_argument('task_id')
        sub.add_argument('--apply', action='store_true')
    args = p.parse_args(argv)
    if not args.command:
        p.print_help(); return 0
    try:
        c = Client(args.base)
        if args.command in ('create', 'record', 'append'):
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
            result = c.write(args.command, parse_json(raw), getattr(args, 'task_id', None), apply=args.apply)
        else:
            result = c.get(args.command, getattr(args, 'task_id', None))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({'error': str(exc)[:240]}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
