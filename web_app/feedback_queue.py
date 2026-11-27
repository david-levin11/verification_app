"""Private SQLite feedback queue and server-side review commands."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
from uuid import uuid4

FEEDBACK_KINDS = ('Bug report', 'Improvement')
TITLE_LIMIT = 120
DETAILS_LIMIT = 5000
CONTACT_LIMIT = 254

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    page TEXT NOT NULL,
    title TEXT NOT NULL,
    details TEXT NOT NULL,
    contact TEXT NOT NULL,
    context_json TEXT,
    resolved_at TEXT
)
"""


def feedback_database():
    configured = os.environ.get('VERIFICATION_FEEDBACK_DB')
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state'
    return Path(state_home) / 'verification-app' / 'feedback.sqlite3'


def _open_queue(path, create=False):
    # Create the database with private permissions before SQLite opens it.
    if create:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or (os.name == 'posix' and stat.S_IMODE(mode) & 0o077):
        raise OSError('The feedback database must be a private regular file.')
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def save_feedback(path, *, kind, page, title, details, contact='', context=None):
    title, details, contact = title.strip(), details.strip(), contact.strip()
    if kind not in FEEDBACK_KINDS:
        raise ValueError('Choose a feedback type.')
    if not title or not details:
        raise ValueError('Enter a summary and a description.')
    if len(title) > TITLE_LIMIT or len(details) > DETAILS_LIMIT or len(contact) > CONTACT_LIMIT:
        raise ValueError('Shorten the summary, description, or contact information.')
    feedback_id = uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    context_json = json.dumps(context, ensure_ascii=False) if context else None
    with closing(_open_queue(path, create=True)) as connection, connection:
        connection.execute(_SCHEMA)
        connection.execute(
            'INSERT INTO feedback (id, created_at, kind, page, title, details, contact, context_json) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (feedback_id, created_at, kind, page, title, details, contact, context_json),
        )
    return feedback_id


def list_feedback(path, status='open'):
    predicates = {'open': 'WHERE resolved_at IS NULL', 'resolved': 'WHERE resolved_at IS NOT NULL', 'all': ''}
    try:
        connection = _open_queue(path)
    except FileNotFoundError:
        return
    with closing(connection):
        for row in connection.execute(f'SELECT * FROM feedback {predicates[status]} ORDER BY created_at, id'):
            report = dict(row)
            context = report.pop('context_json')
            report['context'] = json.loads(context) if context else None
            yield report


def resolve_feedback(path, feedback_id):
    resolved_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    with closing(_open_queue(path)) as connection, connection:
        updated = connection.execute(
            'UPDATE feedback SET resolved_at = COALESCE(resolved_at, ?) WHERE id = ?',
            (resolved_at, feedback_id),
        )
        if not updated.rowcount:
            raise ValueError('Feedback ID was not found.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=feedback_database())
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='Print reports as one JSON object per line')
    listing.add_argument('--status', choices=['open', 'resolved', 'all'], default='open')
    resolve = commands.add_parser('resolve', help='Mark a report resolved')
    resolve.add_argument('id')
    args = parser.parse_args()
    try:
        if args.command == 'list':
            for report in list_feedback(args.database, args.status):
                print(json.dumps(report, ensure_ascii=False))
        else:
            resolve_feedback(args.database, args.id)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f'Feedback queue: {exc}\n')


if __name__ == '__main__':
    main()
