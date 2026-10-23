import json
import threading
import pytest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cartpole_sdk.portal.queue import Store, QueueError
from cartpole_sdk.portal.server import make_server

ORIGIN='https://cartpole.example.com'

@pytest.fixture
def service(tmp_path):
    seen=[]
    class Camera(BaseHTTPRequestHandler):
        def handle_request(self):
            seen.append((self.command,self.path,dict(self.headers)))
            if self.command=='POST':
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                data=json.dumps({'mode':payload['mode']}).encode()
            elif self.path.startswith('/preview.jpg'):data=b'jpeg'
            else:data=b'{"video":{"mode":"tracked"}}'
            if getattr(self.server,'redirect',False):
                self.send_response(302);self.send_header('Location','/calibrate');self.end_headers();return
            self.send_response(200)
            self.send_header('Content-Type','image/jpeg' if self.path.startswith('/preview') else 'application/json')
            self.end_headers();self.wfile.write(data)
        do_GET=handle_request
        do_POST=handle_request
        def log_message(self,*a):pass
    camera=ThreadingHTTPServer(('127.0.0.1',0),Camera)
    portal=make_server(Store(tmp_path),{'alice-secret-long':('alice','submit'),'worker-secret-long':('w','worker')},port=0,origins=[ORIGIN],camera_url=f'http://127.0.0.1:{camera.server_port}')
    for s in (camera,portal):threading.Thread(target=s.serve_forever,daemon=True).start()
    def request(path,method='GET',body=None,origin=ORIGIN,token='alice-secret-long',headers=None):
        h={'Origin':origin,'Authorization':'Bearer '+token,**(headers or {})}
        if body is not None:h['Content-Type']='application/json'
        req=Request(f'http://127.0.0.1:{portal.server_port}'+path,data=json.dumps(body).encode() if body is not None else None,headers=h,method=method)
        try:r=urlopen(req)
        except HTTPError as e:r=e
        with r:return r.status,r.headers,r.read()
    portal.test_camera=camera
    yield request,seen,portal
    for s in (portal,camera):s.shutdown();s.server_close()

def test_preflight_and_cors(service):
    req,seen,_=service
    status,h,_=req('/api/camera','OPTIONS',token='',headers={'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type,x-worker-lease'})
    assert status==204 and h['Access-Control-Allow-Origin']==ORIGIN
    assert 'Origin' in h['Vary'] and not h.get('Access-Control-Allow-Credentials')
    assert req('/api/camera','OPTIONS',headers={'Access-Control-Request-Method':'DELETE'})[0]==403
    assert req('/api/camera',origin='https://evil.example')[0]==403
    assert seen==[]
    assert req('/api/camera',token='bad')[0]==401

def test_camera_contract(service):
    req,seen,_=service
    status,h,body=req('/api/camera')
    assert status==200 and json.loads(body)=={'mode':'overlay','modes':['camera','overlay','mask']}
    assert h['Access-Control-Allow-Origin']==ORIGIN
    assert req('/api/camera/mode','POST',{'mode':'mask'})[0]==200
    assert json.loads(req('/api/camera/mode','POST',{'mode':'overlay'})[2])['mode']=='overlay'
    assert req('/api/camera/mode','POST',{'mode':'calibrate'})[0]==400
    assert req('/api/camera/mode','POST',{'mode':'mask','url':'http://evil'})[0]==400
    assert req('/api/camera',token='worker-secret-long')[0]==403
    assert req('/api/camera/preview?mode=mask')[2]==b'jpeg'
    assert seen[-1][1]=='/preview.jpg?mask=1'
    assert all('Authorization' not in h and 'Cookie' not in h for _,_,h in seen)
    assert json.loads(req('/api/config')[2])['camera_available'] is True

def test_wildcard_origin_rejected(tmp_path):
    with pytest.raises(QueueError):make_server(Store(tmp_path),{'alice-secret-long':('alice','submit')},port=0,origins=['*'])

def test_upstream_redirect_and_size_limit(service,monkeypatch):
    from cartpole_sdk.portal import camera_proxy
    req,seen,portal=service
    portal.test_camera.redirect=True
    assert req('/api/camera')[0]==400
    assert [path for _,path,_ in seen]==['/api/state']
    portal.test_camera.redirect=False
    monkeypatch.setattr(camera_proxy,'MAX_CAMERA_BYTES',2)
    assert req('/api/camera/preview')[0]==400

def test_cors_on_video_response(service):
    req,seen,_=service
    # Mock camera returns JSON rather than H264, so verify the authenticated error has CORS too.
    status,headers,_=req('/api/video')
    assert status==502 and headers['Access-Control-Allow-Origin']==ORIGIN
    seen.clear()
    assert req('/api/video',origin='null')[0]==403
    assert seen==[]

def test_camera_trickle_deadline(service,monkeypatch):
    import time
    from cartpole_sdk.portal import camera_proxy
    req,seen,portal=service
    def trickle(handler):
        try:
            handler.wfile.write(b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n')
            for _ in range(30):
                handler.wfile.write(b' ');handler.wfile.flush();time.sleep(.03)
        except OSError:pass
    monkeypatch.setattr(portal.test_camera.RequestHandlerClass,'do_GET',trickle)
    monkeypatch.setattr(camera_proxy,'CAMERA_SECONDS',.15)
    start=time.monotonic()
    assert req('/api/camera')[0]==400
    assert time.monotonic()-start<.6
