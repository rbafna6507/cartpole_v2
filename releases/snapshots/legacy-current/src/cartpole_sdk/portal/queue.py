"""Durable owner-bound jobs and one transactional lease per physical rig."""
from contextlib import contextmanager, closing
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid
from cartpole_sdk.recording import canonical_json, strict_json_loads

class QueueError(ValueError):
    pass

_TERMINAL=('succeeded','failed','cancelled')

def name(value, label='identifier'):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',value):
        raise QueueError(f'invalid {label}')
    return value

class Store:
    def __init__(self, root):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.blobs=self.root/'artifacts'
        if self.blobs.is_symlink():raise QueueError('artifact directory cannot be a symlink')
        self.blobs.mkdir(mode=0o700,exist_ok=True)
        self.database=self.root/'queue.sqlite3'
        if self.database.is_symlink():raise QueueError('database cannot be a symlink')
        with closing(self._connect()) as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, key TEXT NOT NULL,
              artifact TEXT NOT NULL, filename TEXT NOT NULL, source TEXT NOT NULL,
              duration REAL NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
              updated REAL NOT NULL, worker TEXT, rig TEXT, lease TEXT,
              lease_until REAL, deadline REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
              result TEXT, UNIQUE(owner,key));
            CREATE TABLE IF NOT EXISTS rigs (
              id TEXT PRIMARY KEY, job TEXT, blocked INTEGER NOT NULL DEFAULT 0, reason TEXT);
            ''')
        os.chmod(self.database,0o600)
    def _connect(self):
        db=sqlite3.connect(self.database,timeout=3)
        db.row_factory=sqlite3.Row
        return db
    @contextmanager
    def _tx(self):
        db=self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()
    def _public(self,row, *, worker=False):
        if row is None:raise QueueError('job unavailable')
        result=dict(row)
        result['cancel_requested']=bool(result['cancel_requested'])
        result['result']=None if result['result'] is None else strict_json_loads(result['result'])
        if not worker:
            for field in ('lease','lease_until','worker'):
                result.pop(field,None)
        return result
    def _write_blob(self,source):
        sha=hashlib.sha256(source).hexdigest()
        directory=os.open(self.blobs,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        fd=None
        try:
            try:
                fd=os.open(f'{sha}.py',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400,dir_fd=directory)
                with os.fdopen(fd,'wb') as stream:
                    fd=None;stream.write(source);stream.flush();os.fsync(stream.fileno())
            except FileExistsError:
                try:
                    existing=os.open(f'{sha}.py',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
                    with os.fdopen(existing,'rb') as stream:
                        if stream.read(65537)!=source:raise QueueError('artifact integrity failure')
                except OSError as exc:raise QueueError('unsafe artifact path') from exc
            os.fsync(directory)
        except OSError as exc:raise QueueError('artifact storage failed') from exc
        finally:
            if fd is not None:os.close(fd)
            os.close(directory)
        return sha
    def artifact(self,sha):
        if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{64}',sha):raise QueueError('invalid artifact digest')
        directory=os.open(self.blobs,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            fd=os.open(f'{sha}.py',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            with os.fdopen(fd,'rb') as stream:source=stream.read(65537)
        except OSError as exc:raise QueueError('artifact unavailable') from exc
        finally:os.close(directory)
        if len(source)>65536 or hashlib.sha256(source).hexdigest()!=sha:raise QueueError('artifact integrity failure')
        return source
    def submit(self,owner,key,source,filename,sensor_source,duration,*,now=None):
        name(owner,'owner');name(key,'idempotency key')
        if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,75}\.py',filename):raise QueueError('filename must be a plain .py name')
        if type(source) is not bytes or not 1<=len(source)<=65536:raise QueueError('source must be 1..65536 bytes')
        try:source.decode('utf-8')
        except UnicodeDecodeError as exc:raise QueueError('source must be UTF-8') from exc
        if b'\x00' in source:raise QueueError('source cannot contain NUL')
        if sensor_source not in ('magnetic-step','simulation'):raise QueueError('unsupported explicit source selection')
        if type(duration) not in (int,float) or not .05<=duration<=60:raise QueueError('duration must be 0.05..60 seconds')
        now=time.time() if now is None else now
        sha=hashlib.sha256(source).hexdigest()
        with self._tx() as db:
            prior=db.execute('SELECT * FROM jobs WHERE owner=? AND key=?',(owner,key)).fetchone()
            if prior is not None:
                if (prior['artifact'],prior['filename'],prior['source'],prior['duration'])!=(sha,filename,sensor_source,duration):raise QueueError('idempotency key already binds a different submission')
                return self._public(prior)
            if db.execute("SELECT count(*) FROM jobs WHERE owner=? AND status IN ('pending','claimed','running')",(owner,)).fetchone()[0]>=32:raise QueueError('owner queue limit reached')
            self._write_blob(source)
            identifier=uuid.uuid4().hex
            db.execute('INSERT INTO jobs (id,owner,key,artifact,filename,source,duration,status,created,updated) VALUES (?,?,?,?,?,?,?,\'pending\',?,?)',
                       (identifier,owner,key,sha,filename,sensor_source,duration,now,now))
            return self._public(db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone())
    def get(self,identifier,owner=None):
        name(identifier)
        with closing(self._connect()) as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone()
        if row is None or owner is not None and row['owner']!=owner:raise QueueError('job unavailable')
        return self._public(row)
    def list(self,owner=None):
        with closing(self._connect()) as db:
            rows=db.execute('SELECT * FROM jobs '+('WHERE owner=? ' if owner is not None else '')+'ORDER BY created DESC LIMIT 100',() if owner is None else (owner,)).fetchall()
        return [self._public(row) for row in rows]
    def cancel(self,identifier,owner):
        with self._tx() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(identifier,owner)).fetchone()
            if row is None:raise QueueError('job unavailable')
            if row['status']=='pending':db.execute("UPDATE jobs SET status='cancelled',updated=? WHERE id=?",(time.time(),identifier))
            elif row['status'] in ('claimed','running'):db.execute('UPDATE jobs SET cancel_requested=1,updated=? WHERE id=?',(time.time(),identifier))
            return self._public(db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone())
    def _recover(self,db,now):
        rows=db.execute("SELECT * FROM jobs WHERE status IN ('claimed','running') AND (lease_until<=? OR deadline<=?)",(now,now)).fetchall()
        for row in rows:
            uncertain=row['status']=='running'
            result=canonical_json({'error':'worker lease expired','stopped':False if uncertain else True})
            db.execute("UPDATE jobs SET status='failed',result=?,updated=? WHERE id=?",(result,now,row['id']))
            db.execute('UPDATE rigs SET job=NULL,blocked=?,reason=? WHERE id=?',(int(uncertain),'expired active lease; physical stop must be confirmed' if uncertain else None,row['rig']))
        return len(rows)
    def recover(self,*,now=None):
        with self._tx() as db:return self._recover(db,time.time() if now is None else now)
    def claim(self,worker,rig,*,now=None,sensor_source=None):
        name(worker,'worker');name(rig,'rig')
        if sensor_source is not None and sensor_source not in ('simulation','magnetic-step'):raise QueueError('unsupported explicit source selection')
        now=time.time() if now is None else now
        with self._tx() as db:
            self._recover(db,now)
            db.execute('INSERT OR IGNORE INTO rigs(id) VALUES(?)',(rig,))
            status=db.execute('SELECT * FROM rigs WHERE id=?',(rig,)).fetchone()
            if status['blocked']:raise QueueError('rig blocked pending operator recovery')
            if status['job'] is not None:return None
            row=db.execute("SELECT * FROM jobs WHERE status='pending'"+(" AND source=?" if sensor_source is not None else "")+" ORDER BY created,id LIMIT 1",(sensor_source,) if sensor_source is not None else ()).fetchone()
            if row is None:return None
            token=secrets.token_hex(32)
            db.execute("UPDATE jobs SET status='claimed',worker=?,rig=?,lease=?,lease_until=?,deadline=?,updated=? WHERE id=?",(worker,rig,token,now+2,now+5,now,row['id']))
            db.execute('UPDATE rigs SET job=? WHERE id=?',(row['id'],rig))
            return self._public(db.execute('SELECT * FROM jobs WHERE id=?',(row['id'],)).fetchone(),worker=True)
    def _lease(self,db,identifier,worker,token,now):
        row=db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone()
        if row is None or row['status'] not in ('claimed','running') or row['worker']!=worker or not isinstance(token,str) or not hmac.compare_digest(row['lease'],token) or now>=row['lease_until'] or now>=row['deadline']:
            raise QueueError('inactive or invalid worker lease')
        return row
    def start(self,identifier,worker,token,*,now=None):
        now=time.time() if now is None else now
        with self._tx() as db:
            row=self._lease(db,identifier,worker,token,now)
            if row['status']!='claimed' or row['cancel_requested']:raise QueueError('job cannot start')
            deadline=now+row['duration']+1
            db.execute("UPDATE jobs SET status='running',deadline=?,lease_until=?,updated=? WHERE id=?",(deadline,min(now+2,deadline),now,identifier))
            return self._public(db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone(),worker=True)
    def heartbeat(self,identifier,worker,token,*,now=None):
        now=time.time() if now is None else now
        with self._tx() as db:
            row=self._lease(db,identifier,worker,token,now)
            db.execute('UPDATE jobs SET lease_until=?,updated=? WHERE id=?',(min(now+2,row['deadline']),now,identifier))
            return self._public(db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone(),worker=True)
    def finish(self,identifier,worker,token,status,result,*,now=None):
        if status not in _TERMINAL:raise QueueError('invalid terminal status')
        if not isinstance(result,dict):raise QueueError('result must be an object')
        try:encoded=canonical_json(result)
        except (ValueError,TypeError) as exc:raise QueueError('invalid result') from exc
        if len(encoded.encode())>65536:raise QueueError('result too large')
        now=time.time() if now is None else now
        with self._tx() as db:
            row=self._lease(db,identifier,worker,token,now)
            stopped=result.get('stopped') is True
            if row['cancel_requested'] and stopped:status='cancelled'
            db.execute('UPDATE jobs SET status=?,result=?,updated=? WHERE id=?',(status if stopped else 'failed',encoded,now,identifier))
            db.execute('UPDATE rigs SET job=NULL,blocked=?,reason=? WHERE id=?',(int(not stopped),None if stopped else 'worker cannot confirm physical stop',row['rig']))
            return self._public(db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone())
    def release_block(self,rig,*,stopped_confirmed):
        name(rig,'rig')
        if stopped_confirmed is not True:raise QueueError('operator must confirm stopped rig')
        with self._tx() as db:
            row=db.execute('SELECT * FROM rigs WHERE id=?',(rig,)).fetchone()
            if row is None or row['job'] is not None:raise QueueError('rig unavailable for recovery')
            db.execute('UPDATE rigs SET blocked=0,reason=NULL WHERE id=?',(rig,))
