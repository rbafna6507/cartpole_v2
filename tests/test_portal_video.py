import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cartpole_sdk.portal.queue import Store
from cartpole_sdk.portal.server import make_server


def test_video_proxy_auth_path_and_content(tmp_path):
    seen=[]
    class Camera(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path,self.headers.get('Authorization')))
            self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.end_headers();self.wfile.write(b'camera-packet')
        def log_message(self,*args):pass
    camera=ThreadingHTTPServer(('127.0.0.1',0),Camera)
    portal=make_server(Store(tmp_path),{'alice-secret-long':('alice','submit'),'worker-secret-long':('w','worker')},port=0,camera_url=f'http://127.0.0.1:{camera.server_port}')
    threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (camera,portal)]
    for t in threads:t.start()
    try:
        url=f'http://127.0.0.1:{portal.server_port}/api/video'
        for token in ('bad','worker-secret-long'):
            try:urlopen(Request(url,headers={'Authorization':'Bearer '+token}))
            except HTTPError as exc:assert exc.code in (401,403)
            else:assert False
        with urlopen(Request(url,headers={'Authorization':'Bearer alice-secret-long'})) as r:
            assert r.read()==b'camera-packet'
            assert r.headers['Content-Type'].startswith('application/octet-stream')
        assert seen==[('/video.h264',None)]
        assert portal.video_slots.acquire(blocking=False)
        portal.video_slots.release()
    finally:
        for s in (portal,camera):s.shutdown();s.server_close()
        for t in threads:t.join()


def test_trickling_camera_headers_have_absolute_deadline(tmp_path,monkeypatch):
    import time
    from cartpole_sdk.portal import video_proxy
    monkeypatch.setattr(video_proxy,'VIDEO_SECONDS',.15)
    class SlowCamera(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                self.wfile.write(b'HTTP/1.0 200 OK\r\nX-Test: ')
                for _ in range(20):
                    self.wfile.write(b'x');self.wfile.flush();time.sleep(.04)
            except OSError:pass
        def log_message(self,*args):pass
    camera=ThreadingHTTPServer(('127.0.0.1',0),SlowCamera)
    portal=make_server(Store(tmp_path),{'alice-secret-long':('alice','submit')},port=0,camera_url=f'http://127.0.0.1:{camera.server_port}')
    threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (camera,portal)]
    for t in threads:t.start()
    try:
        began=time.monotonic()
        try:urlopen(Request(f'http://127.0.0.1:{portal.server_port}/api/video',headers={'Authorization':'Bearer alice-secret-long'}),timeout=1)
        except HTTPError as exc:assert exc.code==502
        else:assert False
        assert time.monotonic()-began<.5
    finally:
        for s in (portal,camera):s.shutdown();s.server_close()
        for t in threads:t.join()
