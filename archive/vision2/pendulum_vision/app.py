"""Thread-safe measurement engine and local calibration dashboard API."""
import json
import math
from pathlib import Path
import threading
import time
import cv2
import numpy as np
from flask import Flask,Response,jsonify,request
from .cart import CartTemplate
from .capture import ArrivalStats
from .detector import ArmDetector
from .state import StateEstimator


class Engine:
    def __init__(self, target_fps=80, directory=None):
        self.lock=threading.RLock()
        self.detector=ArmDetector();self.estimator=StateEstimator();self.cart=CartTemplate()
        self.stats=ArrivalStats(target_fps);self.frame=None;self.pose=None;self.mask=None
        self.jpg=None;self.mask_jpg=None;self.last_seq=None;self.skipped=0;self.processed=0
        self.camera=None;self.error=None;self.directory=Path(directory) if directory else None
        self.preview_seq=None;self.recorder=None;self.video=None;self.video_frame=None

    def process(self,frame,t,seq):
        tick=time.perf_counter()
        with self.lock:
            if self.frame is not None and frame.shape!=self.frame.shape:
                self.estimator.reset();self.cart=CartTemplate();self.detector.seed=None
            detection=self.detector.detect(frame)
            cart_pivot,score,cart_reason=self.cart.detect(frame)
            self.frame=frame;self.pose=detection.pose;self.mask=detection.mask
            # Prefer the directly visible screw; use cart appearance through arm occlusion.
            if detection.pose is not None:
                if cart_pivot is not None and np.linalg.norm(np.array(cart_pivot)-detection.pose.pivot)>8:
                    cart_reason='cart template disagrees with screw; reselect patch'
                    self.cart.invalid_reason=cart_reason
                cart_pivot=None
            state=self.estimator.update(detection.pose,t,cart_pivot)
            if self.last_seq is not None:self.skipped+=max(0,seq-self.last_seq-1)
            self.last_seq=seq;self.processed+=1;self.stats.observe(t)
            state.update(seq=seq,detection_status=detection.reason,cart_template_status=cart_reason,
                         cart_match_score=score,processing_ms=(time.perf_counter()-tick)*1000,
                         frame_width=frame.shape[1],frame_height=frame.shape[0],
                         detected=detection.pose is not None)
            self.estimator.last_state.update(state)
            self.video_frame=(seq,t,frame,detection.pose,state['status'],detection.mask)
            return state

    def snapshot(self):
        with self.lock:
            state=self.estimator.snapshot(time.monotonic())
            tracking=self.stats.report()
            if state['stale']:tracking['target_rate_met']=False
            state.update(tracking=tracking,processed_frames=self.processed,skipped_camera_frames=self.skipped,
                         worker_error=self.error,cart_template_selected=self.cart.template is not None,
                         preview_seq=self.preview_seq)
        if self.camera is not None:state['camera']=self.camera.report()
        if self.video is not None:state['video']=self.video.report()
        if self.recorder is not None:
            state['recording']=dict(dropped_frames=self.recorder.dropped,error=self.recorder.error,
                                    written_frames=self.recorder.recorder.count,queued_frames=self.recorder.queue.qsize())
        return state

    def fresh(self):
        if self.estimator.last_t is None or time.monotonic()-self.estimator.last_t>.15:
            raise RuntimeError('No fresh camera measurement')

    def save_event(self,event):
        if self.directory is not None:
            payload=dict(t=time.monotonic(),event=event,calibration=self.estimator.calibration())
            (self.directory/'calibration.json').write_text(json.dumps(payload,indent=2))
            with (self.directory/'events.jsonl').open('a') as log:log.write(json.dumps(payload)+'\n')


def create_app(engine):
    app=Flask(__name__)
    app.config['MAX_CONTENT_LENGTH']=16*1024
    page=Path(__file__).with_name('dashboard.html')

    @app.get('/')
    def index():return page.read_text()

    @app.get('/api/state')
    def state():return jsonify(engine.snapshot())

    @app.get('/snapshot.png')
    def snapshot():
        with engine.lock:
            try:engine.fresh()
            except RuntimeError as e:return jsonify(error=str(e)),409
            frame=engine.frame.copy()
        ok,data=cv2.imencode('.png',frame)
        return Response(data.tobytes(),mimetype='image/png') if ok else (jsonify(error='PNG encoding failed'),500)

    @app.get('/preview.jpg')
    def preview():
        with engine.lock:
            data=engine.mask_jpg if request.args.get('mask')=='1' else engine.jpg
        if data is None:return jsonify(error='Waiting for camera'),503
        return Response(data,mimetype='image/jpeg',headers={'Cache-Control':'no-store'})

    @app.get('/video.js')
    def video_script():
        return Response(page.with_name('video.js').read_text(),mimetype='text/javascript')

    @app.get('/video.h264')
    def video_stream():
        if engine.video is None:return jsonify(error='Video encoder unavailable'),503
        video=engine.video
        viewer=video.hub.subscribe()
        def packets():
            import queue
            try:
                while True:
                    try:packet=viewer.get(timeout=5)
                    except queue.Empty:return
                    if packet is None:return
                    yield packet
            finally:video.hub.unsubscribe(viewer)
        return Response(packets(),mimetype='application/octet-stream',
                        headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.post('/api/video-mode')
    def video_mode():
        if engine.video is None:return jsonify(error='Video encoder unavailable'),503
        body=request.get_json(silent=True)
        if not isinstance(body,dict):return jsonify(error='Expected a JSON object'),400
        try:engine.video.set_mode(body.get('mode'))
        except ValueError as error:return jsonify(error=str(error)),400
        return jsonify(ok=True,mode=engine.video.mode)

    def action(fn):
        with engine.lock:
            try:
                engine.fresh()
                body=request.get_json(silent=True)
                if body is None:body={}
                if not isinstance(body,dict):raise ValueError('Expected a JSON object')
                fn(body)
                engine.save_event(request.path)
            except RuntimeError as error:return jsonify(error=str(error)),409
            except (ValueError,TypeError,KeyError,OverflowError) as error:return jsonify(error=str(error)),400
        return jsonify(ok=True,calibration=engine.estimator.calibration())

    @app.post('/api/home')
    def home():return action(lambda body:engine.estimator.home())

    @app.post('/api/cart/<which>')
    def mark_cart(which):
        return action(lambda body:engine.estimator.mark_cart(which,float(body.get('span_mm',0))))

    @app.post('/api/select')
    def select():
        def apply(body):
            x,y=float(body['x']),float(body['y'])
            if not (math.isfinite(x) and math.isfinite(y) and 0<=x<=1 and 0<=y<=1):
                raise ValueError('Select a point inside the image')
            h,w=engine.frame.shape[:2]
            engine.detector.select(x*w,y*h)
            engine.estimator.reset();engine.cart=CartTemplate()
        return action(apply)

    @app.post('/api/template')
    def template():
        def apply(body):
            if engine.pose is None:raise ValueError('Arm and pivot must be visible while selecting the cart')
            rect=np.array(body['rectangle'],float)
            if rect.shape!=(4,) or not np.all(np.isfinite(rect)) or np.any(rect<0) or np.any(rect>1):
                raise ValueError('Invalid normalized rectangle')
            h,w=engine.frame.shape[:2]
            engine.cart.select(engine.frame,rect*np.array([w,h,w,h]),engine.pose.pivot)
            engine.estimator.cart_velocity.clear();engine.estimator.cart_samples.clear()
        return action(apply)

    @app.post('/api/reset')
    def reset():
        with engine.lock:
            engine.estimator.reset();engine.detector.seed=None;engine.cart=CartTemplate()
            engine.save_event('reset')
        return jsonify(ok=True)

    return app
