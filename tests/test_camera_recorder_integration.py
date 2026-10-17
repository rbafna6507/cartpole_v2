"""Exercise the real spawned recorder, HTTP clocks and bounded latest-frame queue."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import math
import threading
import time
from cartpole_sdk.identification.experiments import CameraRecorder


def test_spawned_camera_capture_preserves_clock_anchors_raw_frames_and_queue(tmp_path):
    stopped=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/api/clock':
                body=json.dumps({'monotonic_s':time.monotonic()}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
            self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
            seq=0
            while not stopped.is_set():
                t=time.monotonic()
                row=dict(schema='cartpole-sensing-stream-v1',stream_seq=seq,host_t=t+.000001,
                    encoder={'packets':[]},vision=dict(seq=seq,t=t,stale=False,worker_error=None,
                    age_since_host_read_s=.000001,detected=True,confidence=.9,image_angle_rad=0.,
                    pivot_px=[100.,100.],bob_px=[100.,200.],length_px=100.,frame_width=640,frame_height=480))
                try:self.wfile.write((json.dumps(row)+'\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):break
                seq+=1;stopped.wait(.02)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    recorder=CameraRecorder(f'http://127.0.0.1:{server.server_port}/api/sensing-stream',tmp_path,5.)
    samples=[]
    try:
        recorder.start();deadline=time.monotonic()+.4
        while time.monotonic()<deadline:
            sample=recorder.latest()
            if sample is not None:samples.append(sample)
            time.sleep(.02)
    finally:
        report=recorder.close();stopped.set();server.shutdown();server.server_close();thread.join(2.)
    assert not recorder.process.is_alive()
    assert 'failure' not in report and report['frames']>=5 and samples
    assert report['clock_sync']['method']=='http-roundtrip-midpoint'
    assert report['clock_sync']['start']['local_after_ns']<report['clock_sync']['end']['local_before_ns']
    rows=[json.loads(line) for line in (tmp_path/'vision.ndjson').read_text().splitlines()]
    assert all(type(row['collector_received_ns']) is int for row in rows)
    assert report['sha256']==hashlib.sha256((tmp_path/'vision.ndjson').read_bytes()).hexdigest()
    assert samples[-1]['vision']['image_angle_rad']==0.
    assert json.loads((tmp_path/'vision-report.json').read_text())==report
