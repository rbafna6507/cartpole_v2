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
        self.video_slots=threading.BoundedSemaphore(4)
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
        self.send_header('Content-Type',kind+('' if kind=='application/zip' else '; charset=utf-8'))
        if kind=='application/zip':self.send_header('Content-Disposition','attachment; filename=cartpole-run.zip')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        camera=self.server.camera_url or ''
        self.send_header('Content-Security-Policy',f"default-src 'self'; img-src 'self' {camera}; media-src 'self' {camera}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
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
            if not mutating and path in ('/','/app.js','/style.css','/video.js'):
                filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/video.js':'video.js'}[path]
                kind={'/':'text/html','/app.js':'text/javascript','/style.css':'text/css','/video.js':'text/javascript'}[path]
                self._respond(200,(Path(__file__).parent/'web'/filename).read_bytes(),kind);return
            principal=self._principal()
            if principal is None:self._respond(401,{'error':'authentication required'});return
            owner,role=principal
            if mutating and self.headers.get('Origin') is not None and self.headers['Origin'] not in self.server.origins:
                self._respond(403,{'error':'origin denied'});return
            recording_upload=mutating and re.fullmatch(r'/api/jobs/[a-f0-9]{32}/recording',path) is not None
            body=self._body() if mutating and not recording_upload else None
            store=self.server.store
            if path=='/api/video' and not mutating:
                if role not in ('submit','operator'):self._respond(403,{'error':'role denied'});return
                from .video_proxy import relay_video
                relay_video(self);return
            if path=='/api/config' and not mutating:
                self._respond(200,{'camera_url':self.server.camera_url,'reservations_enabled':store.reservations_enabled,'rig_id':self.server.rig_id});return
            if path=='/api/reservations':
                if role not in ('submit','operator'):self._respond(403,{'error':'role denied'});return
                if not mutating:
                    self._respond(200,{'enabled':store.reservations_enabled,'reservations':store.reservations(owner if role=='submit' else None)});return
                if role!='submit':self._respond(403,{'error':'role denied'});return
                self._fields(body,('rig','starts_at','duration_minutes'))
                if body['rig']!=self.server.rig_id:raise QueueError('unknown reservation rig')
                self._respond(201,store.reserve(owner,**body));return
            reservation_match=re.fullmatch(r'/api/reservations/([a-f0-9]{32})/cancel',path)
            if reservation_match and mutating:
                if role!='submit':self._respond(403,{'error':'role denied'});return
                self._fields(body,())
                self._respond(200,store.cancel_reservation(reservation_match[1],owner));return
            if path=='/api/me' and not mutating:
                self._respond(200,{'principal':owner,'role':role});return
            if path=='/api/jobs':
                if not mutating:
                    if role not in ('submit','operator'):self._respond(403,{'error':'role denied'});return
                    self._respond(200,{'jobs':store.list(owner if role=='submit' else None)});return
                if role!='submit':self._respond(403,{'error':'role denied'});return
                fields={'source','filename','sensor_source','duration','idempotency_key'}
                if set(body) not in (fields,fields|{'reservation_id'}):raise QueueError('request fields mismatch')
                if not isinstance(body['source'],str):raise QueueError('source must be text')
                job=store.submit(owner,body['idempotency_key'],body['source'].encode('utf-8'),body['filename'],body['sensor_source'],body['duration'],reservation_id=body.get('reservation_id'))
                self._respond(201,job);return
            if path=='/api/claim' and mutating:
                if role!='worker':self._respond(403,{'error':'role denied'});return
                if set(body) not in ({'rig'},{'rig','sensor_source'}):raise QueueError('request fields mismatch')
                self._respond(200,{'job':store.claim(owner,body['rig'],sensor_source=body.get('sensor_source'))});return
            match=re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/(cancel|approve|artifact|recording|start|heartbeat|finish))?',path)
            if match:
                identifier,operation=match.groups()
                if operation is None and not mutating:
                    if role not in ('submit','operator'):self._respond(403,{'error':'role denied'});return
                    self._respond(200,store.get(identifier,owner if role=='submit' else None));return
                if operation=='recording':
                    if not mutating:
                        if role not in ('submit','operator'):self._respond(403,{'error':'role denied'});return
                        self._respond(200,store.recording(identifier,owner if role=='submit' else None),'application/zip');return
                    if role!='worker':self._respond(403,{'error':'role denied'});return
                    from .run_recording import MAX_BUNDLE_BYTES
                    lengths=self.headers.get_all('Content-Length',[])
                    if self.headers.get('Transfer-Encoding') is not None or len(lengths)!=1 or not re.fullmatch('[0-9]{1,8}',lengths[0]):raise QueueError('invalid recording body framing')
                    size=int(lengths[0])
                    if not 1<=size<=MAX_BUNDLE_BYTES:raise QueueError('invalid recording size')
                    if self.headers.get_content_type()!='application/zip':raise QueueError('ZIP body required')
                    lease=self.headers.get('X-Worker-Lease','')
                    # Authorize before accepting a potentially large body.
                    with closing(store._connect()) as db:
                        row=db.execute('SELECT worker,lease,status FROM jobs WHERE id=?',(identifier,)).fetchone()
                    if row is None or row['status'] not in ('succeeded','failed','cancelled') or row['worker']!=owner or not isinstance(row['lease'],str) or not hmac.compare_digest(row['lease'],lease):
                        self._respond(403,{'error':'recording worker identity mismatch'});return
                    self.rfile.deadline=time.monotonic()+30
                    raw=self.rfile.read(size)
                    if len(raw)!=size:raise QueueError('incomplete recording body')
                    self._respond(200,store.put_recording(identifier,owner,lease,raw));return
                if operation=='approve' and mutating:
                    if role!='operator':self._respond(403,{'error':'role denied'});return
                    self._fields(body,('artifact','sensor_source','duration'))
                    self._respond(200,store.approve(identifier,owner,**body));return
                if operation=='cancel' and mutating:
                    if role!='submit':self._respond(403,{'error':'role denied'});return
                    self._fields(body,());self._respond(200,store.cancel(identifier,owner));return
                if operation=='artifact' and not mutating:
                    if role not in ('worker','operator'):self._respond(403,{'error':'role denied'});return
                    with closing(store._connect()) as db:
                        if role=='operator':row=db.execute('SELECT artifact FROM jobs WHERE id=?',(identifier,)).fetchone()
                        else:row=db.execute("SELECT artifact FROM jobs WHERE id=? AND worker=? AND status IN ('claimed','running')",(identifier,owner)).fetchone()
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
            self._respond(404 if str(exc) in ('job unavailable','recording unavailable','reservation unavailable') else 400,{'error':str(exc)})
        except (TimeoutError,socket.timeout):
            self._respond(408,{'error':'request timeout'})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            self._respond(500,{'error':'service error'})

def make_server(store,credentials,*,host='127.0.0.1',port=8765,origins=(),camera_url=None,rig_id='cartpole'):
    if not isinstance(credentials,dict) or not credentials:raise QueueError('credentials required')
    for token,principal in credentials.items():
        if not isinstance(token,str) or len(token)<12 or not isinstance(principal,(tuple,list)) or len(principal)!=2 or principal[1] not in ('submit','worker','operator'):raise QueueError('invalid credential configuration')
        name(principal[0],'principal')
    name(rig_id,'rig')
    if camera_url is not None:
        parsed=urlsplit(camera_url)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment
                or re.search(r"[\s;'\"<>]",camera_url)):
            raise QueueError('camera URL must be a plain HTTP(S) origin')
        camera_url=camera_url.rstrip('/')
    server=PortalServer((host,port),Handler)
    server.camera_url=camera_url;server.rig_id=rig_id
    server.store=store;server.credentials=credentials.copy()
    server.origins=set(origins)|{f'http://{host}:{server.server_port}'}
    return server

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--credentials',required=True)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--origin',action='append',default=[])
    parser.add_argument('--camera-url',help='read-only camera origin for browser preview')
    parser.add_argument('--enable-reservations',action='store_true')
    parser.add_argument('--rig-id',default='cartpole')
    args=parser.parse_args(argv)
    credentials=strict_json_loads(Path(args.credentials).read_text())
    server=make_server(Store(args.root,reservations_enabled=args.enable_reservations),credentials,host=args.host,port=args.port,origins=args.origin,camera_url=args.camera_url,rig_id=args.rig_id)
    print(f'portal listening at http://{args.host}:{server.server_port}; public hosting is not configured')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0
