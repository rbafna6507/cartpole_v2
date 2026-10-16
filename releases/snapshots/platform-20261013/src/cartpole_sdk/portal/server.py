"""Bounded loopback-first HTTP API; browser credentials never appear in URLs."""
from contextlib import closing
import argparse
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import re
import socket
import threading
import time
from urllib.parse import urlsplit
from cartpole_sdk.recording import canonical_json, strict_json_loads
from .queue import Store, QueueError, name

MAX_BODY=100_000

class _LimitedReader:
    def __init__(self,stream,connection,seconds):
        self.stream=stream;self.connection=connection
        self.deadline=time.monotonic()+seconds;self.pending=bytearray()
    def _chunk(self,size):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('absolute request deadline')
        self.connection.settimeout(remaining)
        return self.stream.read1(size)
    def readline(self,size=-1):
        maximum=min(8193,size) if size>=0 else 8193
        while True:
            newline=self.pending.find(b'\n')
            if newline>=0 and newline<maximum:
                line=bytes(self.pending[:newline+1]);del self.pending[:newline+1]
                if len(line)>8192:raise http.client.LineTooLong('request line')
                return line
            if len(self.pending)>=maximum:raise http.client.LineTooLong('request line')
            chunk=self._chunk(min(4096,maximum-len(self.pending)))
            if not chunk:
                line=bytes(self.pending);self.pending.clear();return line
            self.pending.extend(chunk)
    def read(self,size):
        value=bytearray(self.pending[:size]);del self.pending[:len(value)]
        while len(value)<size:
            chunk=self._chunk(min(4096,size-len(value)))
            if not chunk:break
            value.extend(chunk)
        return bytes(value)
    def __getattr__(self,key):return getattr(self.stream,key)

class PortalServer(ThreadingHTTPServer):
    daemon_threads=True
    request_timeout=3
    allow_reuse_address=True
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except BaseException:self.slots.release();raise
    def process_request_thread(self,*args):
        try:super().process_request_thread(*args)
        finally:self.slots.release()

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    def setup(self):
        self.request.settimeout(3)
        super().setup()
        self.rfile=_LimitedReader(self.rfile,self.request,self.server.request_timeout)
    def log_message(self,*args):pass
    def _respond(self,status,value,kind='application/json'):
        body=canonical_json(value).encode() if kind=='application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',kind+'; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers();self.wfile.write(body)
    def _principal(self):
        header=self.headers.get('Authorization','')
        candidate=header[7:] if header.startswith('Bearer ') else ''
        selected=None
        for token,principal in self.server.credentials.items():
            if hmac.compare_digest(candidate.encode(),token.encode()):selected=principal
        return selected
    def _body(self):
        if self.headers.get('Transfer-Encoding') is not None:raise QueueError('unsupported body framing')
        lengths=self.headers.get_all('Content-Length',[])
        if len(lengths)!=1 or not re.fullmatch('[0-9]{1,6}',lengths[0]):raise QueueError('invalid body length')
        size=int(lengths[0])
        if size>MAX_BODY:raise QueueError('body too large')
        if self.headers.get_content_type()!='application/json':raise QueueError('JSON body required')
        body=self.rfile.read(size)
        if len(body)!=size:raise QueueError('incomplete body')
        try:data=strict_json_loads(body.decode())
        except (ValueError,UnicodeError) as exc:raise QueueError('invalid JSON') from exc
        if not isinstance(data,dict):raise QueueError('JSON object required')
        return data
    def _fields(self,data,fields):
        if set(data)!=set(fields):raise QueueError('request fields mismatch')
    def do_GET(self):self._dispatch(False)
    def do_POST(self):self._dispatch(True)
    def _dispatch(self,mutating):
        try:
            if len(self.headers)>64 or sum(len(k)+len(v) for k,v in self.headers.items())>16384:
                self._respond(431,{'error':'headers too large'});return
            path=urlsplit(self.path).path
            if not mutating and path in ('/','/app.js','/style.css'):
                filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
                kind={'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[path]
                self._respond(200,(Path(__file__).parent/'web'/filename).read_bytes(),kind);return
            principal=self._principal()
            if principal is None:self._respond(401,{'error':'authentication required'});return
            owner,role=principal
            if mutating and self.headers.get('Origin') is not None and self.headers['Origin'] not in self.server.origins:
                self._respond(403,{'error':'origin denied'});return
            body=self._body() if mutating else None
            store=self.server.store
            if path=='/api/jobs':
                if not mutating:
                    if role not in ('submit','operator'):self._respond(403,{'error':'role denied'});return
                    self._respond(200,{'jobs':store.list(owner if role=='submit' else None)});return
                if role!='submit':self._respond(403,{'error':'role denied'});return
                self._fields(body,('source','filename','sensor_source','duration','idempotency_key'))
                if not isinstance(body['source'],str):raise QueueError('source must be text')
                job=store.submit(owner,body['idempotency_key'],body['source'].encode('utf-8'),body['filename'],body['sensor_source'],body['duration'])
                self._respond(201,job);return
            if path=='/api/claim' and mutating:
                if role!='worker':self._respond(403,{'error':'role denied'});return
                if set(body) not in ({'rig'},{'rig','sensor_source'}):raise QueueError('request fields mismatch')
                self._respond(200,{'job':store.claim(owner,body['rig'],sensor_source=body.get('sensor_source'))});return
            match=re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/(cancel|artifact|start|heartbeat|finish))?',path)
            if match:
                identifier,operation=match.groups()
                if operation is None and not mutating:
                    if role not in ('submit','operator'):self._respond(403,{'error':'role denied'});return
                    self._respond(200,store.get(identifier,owner if role=='submit' else None));return
                if operation=='cancel' and mutating:
                    if role!='submit':self._respond(403,{'error':'role denied'});return
                    self._fields(body,());self._respond(200,store.cancel(identifier,owner));return
                if operation=='artifact' and not mutating:
                    if role!='worker':self._respond(403,{'error':'role denied'});return
                    with closing(store._connect()) as db:row=db.execute("SELECT artifact FROM jobs WHERE id=? AND worker=? AND status IN ('claimed','running')",(identifier,owner)).fetchone()
                    if row is None:raise QueueError('job unavailable')
                    source=store.artifact(row['artifact'])
                    self._respond(200,{'sha256':row['artifact'],'source_base64':base64.b64encode(source).decode()});return
                if operation in ('start','heartbeat','finish') and mutating:
                    if role!='worker':self._respond(403,{'error':'role denied'});return
                    self._fields(body,('lease','status','result') if operation=='finish' else ('lease',))
                    if operation=='finish':result=store.finish(identifier,owner,body['lease'],body['status'],body['result'])
                    else:result=getattr(store,operation)(identifier,owner,body['lease'])
                    self._respond(200,result);return
            match=re.fullmatch(r'/api/rigs/([A-Za-z0-9_.-]{1,80})/recover',path)
            if match and mutating:
                if role!='operator':self._respond(403,{'error':'role denied'});return
                self._fields(body,('stopped_confirmed',))
                store.release_block(match[1],stopped_confirmed=body['stopped_confirmed'])
                self._respond(200,{'recovered':True});return
            self._respond(404,{'error':'resource unavailable'})
        except QueueError as exc:
            self._respond(404 if str(exc)=='job unavailable' else 400,{'error':str(exc)})
        except (TimeoutError,socket.timeout):
            self._respond(408,{'error':'request timeout'})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            self._respond(500,{'error':'service error'})

def make_server(store,credentials,*,host='127.0.0.1',port=8765,origins=()):
    if not isinstance(credentials,dict) or not credentials:raise QueueError('credentials required')
    for token,principal in credentials.items():
        if not isinstance(token,str) or len(token)<12 or not isinstance(principal,(tuple,list)) or len(principal)!=2 or principal[1] not in ('submit','worker','operator'):raise QueueError('invalid credential configuration')
        name(principal[0],'principal')
    server=PortalServer((host,port),Handler)
    server.store=store;server.credentials=credentials.copy()
    server.origins=set(origins)|{f'http://{host}:{server.server_port}'}
    return server

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--credentials',required=True)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--origin',action='append',default=[])
    args=parser.parse_args(argv)
    credentials=strict_json_loads(Path(args.credentials).read_text())
    server=make_server(Store(args.root),credentials,host=args.host,port=args.port,origins=args.origin)
    print(f'portal listening at http://{args.host}:{server.server_port}; public hosting is not configured')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0
