"""Headless Jetson USB camera tracker + browser preview. No motor/network control."""
import argparse,csv,json,threading,time
from pathlib import Path
import cv2
from flask import Flask,Response,jsonify,request
from vision import Tracker

PAGE='''<!doctype html><title>Pendulum tracker</title><h2>Pendulum camera proof of concept</h2><p>Green marker at pivot; blue at tip. Hold hanging still before setting zero.</p><button onclick="fetch('/home',{method:'POST'}).then(r=>r.json()).then(x=>alert(JSON.stringify(x)))">Set hanging zero</button> <button onclick="fetch('/clear',{method:'POST'})">Clear calibration</button><p><img src="/stream" style="max-width:100%"></p><pre id="s"></pre><script>setInterval(()=>fetch('/state').then(r=>r.json()).then(x=>document.getElementById('s').textContent=JSON.stringify(x,null,2)),250)</script>'''

class Camera:
    def __init__(self,a):
        self.lock=threading.Lock();self.latest=None;self.seq=0;self.stop=False
        self.cap=cv2.VideoCapture(a.camera,cv2.CAP_V4L2)
        if not self.cap.isOpened():raise RuntimeError('Cannot open camera. Check /dev/video*, permissions and other camera apps.')
        self.cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*a.fourcc))
        for k,v in [(cv2.CAP_PROP_FRAME_WIDTH,a.width),(cv2.CAP_PROP_FRAME_HEIGHT,a.height),(cv2.CAP_PROP_FPS,a.fps),(cv2.CAP_PROP_BUFFERSIZE,1)]:self.cap.set(k,v)
        print('Requested mode is not guaranteed; negotiated:',[self.cap.get(k) for k in [cv2.CAP_PROP_FRAME_WIDTH,cv2.CAP_PROP_FRAME_HEIGHT,cv2.CAP_PROP_FPS]])
        threading.Thread(target=self.run,daemon=True).start()
    def run(self):
        while not self.stop:
            ok,f=self.cap.read();t=time.monotonic()
            if not ok:time.sleep(.01);continue
            with self.lock:self.seq+=1;self.latest=(self.seq,t,f)
        self.cap.release()
    def get(self):
        with self.lock:return self.latest

def main():
    p=argparse.ArgumentParser();p.add_argument('--camera',default='/dev/video0');p.add_argument('--width',type=int,default=960);p.add_argument('--height',type=int,default=600);p.add_argument('--fps',type=int,default=80);p.add_argument('--fourcc',default='MJPG');p.add_argument('--bind',default='127.0.0.1');p.add_argument('--port',type=int,default=8080);p.add_argument('--config',default='tracker.json');p.add_argument('--preview-fps',type=float,default=15);p.add_argument('--out',default='vision_runs');a=p.parse_args()
    if len(a.fourcc)!=4 or a.preview_fps<=0:p.error('fourcc must have 4 characters; preview fps must be positive')
    cfg=json.loads(Path(a.config).read_text());tracker=Tracker(cfg);cam=Camera(a);lock=threading.Lock();shared={'state':{'valid':False},'jpg':None};app=Flask(__name__)
    out=Path(a.out)/time.strftime('%Y%m%d_%H%M%S');out.mkdir(parents=True,exist_ok=False)
    (out/'session.json').write_text(json.dumps(vars(a),indent=2));(out/'initial_tracker.json').write_text(json.dumps(cfg,indent=2))
    def worker():
        last=-1;preview=0;previous_t=None
        with (out/'angles.csv').open('w',newline='') as f:
            fields=['seq','host_read_s','valid','theta_down_rad','theta_upright_rad','omega_rad_s','pivot_px','tip_px','processing_ms'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            while not cam.stop:
                item=cam.get()
                if item is None or item[0]==last:time.sleep(.001);continue
                seq,t,frame=item;last=seq;start=time.monotonic()
                with lock:
                    state=tracker.process(frame,t);state.update(seq=seq,host_read_s=t,processing_ms=(time.monotonic()-start)*1000,processed_fps=None if previous_t is None else 1/max(t-previous_t,1e-9));shared['state']=state
                previous_t=t;w.writerow({k:state.get(k) for k in fields})
                if seq%80==0:f.flush()
                if start-preview>=1/a.preview_fps:
                    preview=start;display=frame.copy()
                    for name,color in [('pivot_px',(0,255,0)),('tip_px',(255,0,0))]:
                        if state[name] is not None:cv2.circle(display,tuple(map(round,state[name])),9,color,2)
                    label=f"down {state['theta_down_rad']*180/3.14159265:+.1f} deg" if state['valid'] else 'NOT VALID / set hanging zero'
                    cv2.putText(display,label,(15,35),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,255,255),2)
                    ok,jpg=cv2.imencode('.jpg',display,[cv2.IMWRITE_JPEG_QUALITY,75])
                    if ok:
                        with lock:shared['jpg']=jpg.tobytes()
    @app.get('/')
    def index():return PAGE
    @app.get('/state')
    def state():
        with lock:s=dict(shared['state'])
        s['age_since_host_read_s']=time.monotonic()-s.get('host_read_s',0)
        if s['age_since_host_read_s']>.1:s.update(valid=False,theta_down_rad=None,theta_upright_rad=None,omega_rad_s=None)
        return jsonify(s)
    @app.post('/home')
    def home():
        with lock:
            if time.monotonic()-shared['state'].get('host_read_s',0)>.1:return jsonify(error='Camera stale'),409
            try:tracker.home()
            except ValueError as e:return jsonify(error=str(e)),409
            Path(a.config).write_text(json.dumps(tracker.cfg,indent=2));(out/'home_calibration.json').write_text(json.dumps(tracker.cfg,indent=2))
            with (out/'calibration_events.jsonl').open('a') as ef:ef.write(json.dumps(dict(t=time.monotonic(),event='home',config=tracker.cfg))+'\n')
        return jsonify(ok=True)
    @app.post('/clear')
    def clear():
        with lock:
            tracker.cfg.update(home_angle_rad=None,home_length_px=None);tracker.history.clear();tracker.previous=None
            with (out/'calibration_events.jsonl').open('a') as ef:ef.write(json.dumps(dict(t=time.monotonic(),event='clear'))+'\n')
            Path(a.config).write_text(json.dumps(tracker.cfg,indent=2))
        return jsonify(ok=True)
    @app.get('/stream')
    def stream():
        def frames():
            while not cam.stop:
                with lock:j=shared['jpg']
                if j:yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+j+b'\r\n'
                time.sleep(1/a.preview_fps)
        return Response(frames(),mimetype='multipart/x-mixed-replace; boundary=frame')
    processing_thread=threading.Thread(target=worker,daemon=True);processing_thread.start()
    print('Logging to',out,'; open browser at bind address/port. Ctrl-C stops.')
    try:app.run(host=a.bind,port=a.port,threaded=True,use_reloader=False)
    finally:cam.stop=True;processing_thread.join(timeout=2)
if __name__=='__main__':main()
