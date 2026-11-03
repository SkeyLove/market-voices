"""Private SQLite state with transactional receipts, revisions and budget reservations."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .contracts import Raw, Source, Summary, digest, timestamp


class Store:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.directory/'voices.sqlite3'
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS raw(id TEXT PRIMARY KEY,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS summaries(id TEXT PRIMARY KEY,data TEXT NOT NULL,approval TEXT,approved_hash TEXT);
                CREATE TABLE IF NOT EXISTS editions(id TEXT PRIMARY KEY,data TEXT NOT NULL,approved INTEGER NOT NULL,backup INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS windows(id TEXT PRIMARY KEY,status TEXT NOT NULL,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS budget(id TEXT PRIMARY KEY,month TEXT NOT NULL,reserved REAL NOT NULL,actual REAL,status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,data TEXT NOT NULL);
            ''')
        os.chmod(self.path,0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30)
        db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def set(self,key,value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,json.dumps(value)))

    def get(self,key,default=None):
        with self.db() as db:
            row=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
            return json.loads(row[0]) if row else default

    def event(self,kind,**values):
        with self.db() as db:
            db.execute('INSERT INTO events(data) VALUES (?)',(json.dumps({'kind':kind,'at':timestamp(),**values}),))

    def register(self,source):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)',(source.id,source.model_dump_json()))

    def sources(self):
        with self.db() as db:
            return {r['id']:Source.model_validate_json(r['data']) for r in db.execute('SELECT * FROM sources')}

    def ingest(self,raw):
        key=digest(raw.url)
        with self.db() as db:
            old=db.execute('SELECT data FROM raw WHERE id=?',(key,)).fetchone()
            if old:
                previous=Raw.model_validate_json(old[0])
                # A later fetch time alone must not invalidate inference caches.
                raw=raw.model_copy(update={'collected':previous.collected})
            db.execute('INSERT OR REPLACE INTO raw VALUES (?,?)',(key,raw.model_dump_json()))
        return key

    def records(self):
        with self.db() as db:
            rows=db.execute('SELECT r.id,r.data,s.data summary,s.approval,s.approved_hash FROM raw r LEFT JOIN summaries s ON s.id=r.id').fetchall()
        return [(r['id'],Raw.model_validate_json(r['data']),Summary.model_validate_json(r['summary']) if r['summary'] else None,r['approval'],r['approved_hash']) for r in rows]

    def save_summary(self,key,summary):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO summaries VALUES (?,?,NULL,NULL)',(key,summary.model_dump_json()))

    def approve(self,key,expected_hash,reviewer):
        if not reviewer.strip():
            raise ValueError('reviewer_required')
        with self.db() as db:
            row=db.execute('SELECT data FROM summaries WHERE id=?',(key,)).fetchone()
            if not row or digest(json.loads(row[0]))!=expected_hash:
                raise ValueError('summary_changed')
            db.execute('UPDATE summaries SET approval=?,approved_hash=? WHERE id=?',
                       (reviewer,expected_hash,key))
        self.event('summary_approved',id=key,reviewer=reviewer)

    def reserve(self,request_id,month,amount,cap):
        if amount<=0 or cap<=0:
            raise ValueError('invalid_budget')
        with self.db() as db:
            spent=db.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM budget WHERE month=?',(month,)).fetchone()[0]
            if spent+amount>cap:
                raise ValueError('budget_exhausted')
            db.execute('INSERT INTO budget VALUES (?,?,?,NULL,?)',(request_id,month,amount,'reserved'))

    def settle(self,request_id,actual):
        with self.db() as db:
            row=db.execute('SELECT reserved FROM budget WHERE id=?',(request_id,)).fetchone()
            if not row or actual<0 or actual>row[0]:
                raise ValueError('usage_exceeds_reservation')
            db.execute('UPDATE budget SET actual=?,status=? WHERE id=?',(actual,'settled',request_id))

    def metrics(self):
        with self.db() as db:
            return {'events':[json.loads(r[0]) for r in db.execute('SELECT data FROM events ORDER BY id DESC LIMIT 100')],
                    'budget':[dict(r) for r in db.execute('SELECT month,SUM(COALESCE(actual,reserved)) charged_cny,COUNT(*) requests FROM budget GROUP BY month')],
                    'windows':[dict(r) for r in db.execute('SELECT * FROM windows ORDER BY id DESC LIMIT 30')]}
