"""Library-scoped Agent records. Separate additive database; no asset migrations."""
from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from . import library

LOCK = threading.RLock()


def root():
    if library.PATHS is None:
        raise ValueError('素材库尚未打开')
    path = library.PATHS.data / 'agent'
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_id():
    return hashlib.sha256(str(library.PATHS.data.resolve()).encode()).hexdigest()[:24]


@contextlib.contextmanager
def connect():
    conn = sqlite3.connect(root() / 'agent.db', timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS records (
        kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
        updated REAL NOT NULL, PRIMARY KEY(kind,id));
      CREATE TABLE IF NOT EXISTS events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        body TEXT NOT NULL, created REAL NOT NULL);
    ''')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def put(kind, data):
    with LOCK, connect() as conn:
        data['updated'] = time.time()
        conn.execute('INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body,updated=excluded.updated',
                     (kind, data['id'], json.dumps(data, ensure_ascii=False), data['updated']))
    return data


def get(kind, ident):
    with LOCK, connect() as conn:
        row = conn.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, ident)).fetchone()
    if not row:
        raise ValueError('记录不存在')
    return json.loads(row[0])


def all_records(kind):
    with LOCK, connect() as conn:
        return [json.loads(r[0]) for r in conn.execute('SELECT body FROM records WHERE kind=? ORDER BY updated DESC', (kind,))]


def emit(session_id, event_type, **fields):
    body = {'type': event_type, **fields}
    with LOCK, connect() as conn:
        cur = conn.execute('INSERT INTO events(session_id,body,created) VALUES (?,?,?)',
                           (session_id, json.dumps(body, ensure_ascii=False), time.time()))
        return cur.lastrowid


def events(session_id, after=0):
    with LOCK, connect() as conn:
        return [{'seq': r['seq'], **json.loads(r['body'])} for r in conn.execute(
            'SELECT seq,body FROM events WHERE session_id=? AND seq>? ORDER BY seq LIMIT 500', (session_id, after))]


def new_id():
    return uuid.uuid4().hex
