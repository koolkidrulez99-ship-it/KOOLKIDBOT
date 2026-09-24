import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def data_dir():
    path = Path(os.environ.get('KOOLKID_INTELLIGENCE_DIR') or
                Path(__file__).resolve().parents[1] / 'instance/deriv_intelligence').resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


class Store:
    def __init__(self, path=None):
        self.path = str(path or data_dir() / 'research.sqlite3')
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ticks(
                    id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, epoch REAL NOT NULL,
                    quote TEXT NOT NULL, precision INTEGER NOT NULL, digit INTEGER NOT NULL,
                    received REAL NOT NULL, connection TEXT NOT NULL, origin TEXT NOT NULL,
                    seq INTEGER NOT NULL, UNIQUE(symbol,seq));
                CREATE INDEX IF NOT EXISTS ticks_symbol_time ON ticks(symbol,epoch);
                CREATE INDEX IF NOT EXISTS ticks_retention ON ticks(received);
                CREATE TABLE IF NOT EXISTS markets(symbol TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS setups(
                    id TEXT PRIMARY KEY, symbol TEXT, strategy TEXT, seq INTEGER,
                    created REAL, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS setups_lookup ON setups(symbol,strategy,seq);
                CREATE TABLE IF NOT EXISTS papers(
                    id TEXT PRIMARY KEY, symbol TEXT, strategy TEXT, entry_seq INTEGER,
                    exit_seq INTEGER, created REAL, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS paper_windows ON papers(symbol,strategy,entry_seq,exit_seq);
                CREATE TABLE IF NOT EXISTS payouts(
                    id INTEGER PRIMARY KEY, symbol TEXT, observed REAL, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS payout_lookup ON payouts(symbol,observed);
                CREATE TABLE IF NOT EXISTS snapshots(
                    window TEXT PRIMARY KEY, updated REAL, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS confirmation_decisions(
                    id INTEGER PRIMARY KEY, owner TEXT NOT NULL, created REAL NOT NULL, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS confirmation_owner ON confirmation_decisions(owner,id);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, json.dumps(value)))

    def snapshot(self, window):
        with self.connect() as db:
            row = db.execute('SELECT updated,value FROM snapshots WHERE window=?', (window,)).fetchone()
        return {'updated': row[0], 'rows': json.loads(row[1])} if row else {'updated': None, 'rows': []}

    def record_decision(self, owner, result):
        with self.connect() as db:
            db.execute('INSERT INTO confirmation_decisions(owner,created,value) VALUES(?,?,?)',
                       (owner, result['created'], json.dumps(result)))
            db.execute('DELETE FROM confirmation_decisions WHERE id < (SELECT MAX(id)-10000 FROM confirmation_decisions)')

    def decisions(self, owner, limit=30):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                'SELECT value FROM confirmation_decisions WHERE owner=? ORDER BY id DESC LIMIT ?', (owner, limit))]

    def history(self, symbol, strategy, limit=50):
        with self.connect() as db:
            rows = db.execute('SELECT value FROM papers WHERE symbol=? AND strategy=? ORDER BY exit_seq DESC LIMIT ?',
                              (symbol, strategy, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_ticks(self, rows):
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO ticks(symbol,epoch,quote,precision,digit,received,connection,origin,seq) VALUES(?,?,?,?,?,?,?,?,?)', rows)

    def prune(self, days):
        # Only raw ticks expire. Paper outcomes and all-data statistics remain intact.
        with self.connect() as db:
            db.execute('DELETE FROM ticks WHERE id IN (SELECT id FROM ticks WHERE received<? LIMIT 10000)',
                       (time.time() - days * 86400,))


class Secrets:
    def __init__(self, store):
        self.store = store

    def _cipher(self):
        from cryptography.fernet import Fernet
        key = os.environ.get('KOOLKID_INTELLIGENCE_KEY')
        if not key:
            path = Path(self.store.path).parent / 'credential.key'
            if not path.exists():
                if self.store.get('encrypted_pat'):
                    raise ValueError('Restore the original intelligence encryption key to read the saved PAT.')
                try:
                    with path.open('xb') as handle:
                        handle.write(Fernet.generate_key())
                except FileExistsError:
                    pass
            key = path.read_text(encoding='ascii').strip()
        return Fernet(key.encode())

    def save(self, token):
        if not isinstance(token, str) or not 8 <= len(token.strip()) <= 4096:
            raise ValueError('Enter a valid global PAT.')
        self.store.set('encrypted_pat', self._cipher().encrypt(token.strip().encode()).decode())

    def load(self):
        encrypted = self.store.get('encrypted_pat')
        if encrypted:
            return self._cipher().decrypt(encrypted.encode()).decode()
        return os.environ.get('KOOLKID_GLOBAL_DERIV_PAT', '').strip()

    def configured(self):
        return bool(self.store.get('encrypted_pat') or os.environ.get('KOOLKID_GLOBAL_DERIV_PAT'))
