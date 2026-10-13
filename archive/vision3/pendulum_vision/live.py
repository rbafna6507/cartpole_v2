"""Run the 80 FPS observe-only cartpole vision dashboard."""
import argparse
import json
import logging
from pathlib import Path
import threading
import time
import cv2
from werkzeug.serving import make_server
from .app import Engine,create_app
from .capture import Camera,BufferedRecorder
from .preview import PreviewWorker
from .stream import VideoStream
from .comparison_process import ComparisonProcess


def arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--camera',default='0');p.add_argument('--width',type=int,default=960)
    p.add_argument('--height',type=int,default=600);p.add_argument('--fps',type=int,default=80)
    p.add_argument('--rotate',type=int,choices=(0,90,180,270),default=180)
    p.add_argument('--port',type=int,default=3090);p.add_argument('--preview-fps',type=float,default=1)
    p.add_argument('--detector-width',type=int,default=640,help='Detection image width; endpoints remain in camera coordinates')
    p.add_argument('--opencv-threads',type=int,default=2)
    p.add_argument('--video-fps',type=int,help='H.264 frame-rate cap; defaults to capture FPS')
    p.add_argument('--no-video',action='store_true',help='Disable H.264 to measure tracking without video encoding load')
    p.add_argument('--video-bitrate',type=int,default=4000,help='H.264 target bitrate, kbit/s')
    p.add_argument('--gst-python',default='/usr/bin/python3',help='Python with the installed GStreamer GI runtime')
    p.add_argument('--calibration-file',type=Path,help='Restore saved vision reference for identical camera geometry; update it on calibration changes')
    p.add_argument('--encoder-port',type=int,default=3096,help='Loopback UDP feed from console; 0 disables')
    p.add_argument('--encoder-sign',type=int,choices=(-1,1),default=1,help='Encoder direction relative to image-right')
    p.add_argument('--vision-delay-ms',type=float,default=0,help='Measured camera delay to subtract from host-read timestamp')
    p.add_argument('--out',type=Path,default=Path('runs'));p.add_argument('--record',action='store_true')
    p.add_argument('--duration',type=float,help='Stop automatically after this many seconds')
    p.add_argument('--exposure-raw',type=float,help='Backend-specific exposure value; acceptance/readback logged')
    p.add_argument('--auto-exposure-raw',type=float,help='Backend-specific auto-exposure mode')
    p.add_argument('--gain-raw',type=float,help='Backend-specific gain value')
    a=p.parse_args(argv)
    if a.video_fps is None:a.video_fps=a.fps
    import math
    if min(a.width,a.height,a.fps,a.video_fps,a.video_bitrate,a.detector_width,a.opencv_threads)<=0 or not math.isfinite(a.preview_fps) or a.preview_fps<=0:p.error('Dimensions and rates must be positive')
    if a.duration is not None and (not math.isfinite(a.duration) or a.duration<=0):p.error('duration must be positive')
    for value in (a.exposure_raw,a.auto_exposure_raw,a.gain_raw):
        if value is not None and not math.isfinite(value):p.error('Camera control values must be finite')
    if not 0<=a.encoder_port<=65535:p.error('encoder port must be 0..65535')
    if not math.isfinite(a.vision_delay_ms) or not 0<=a.vision_delay_ms<=200:p.error('vision delay must be 0..200 ms')
    return a


def main():
    a=arguments()
    cv2.setNumThreads(a.opencv_threads)
    directory=a.out/(time.strftime('%Y%m%d_%H%M%S')+f'_{time.time_ns()%1000000:06d}')
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'session.json').write_text(json.dumps({k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},indent=2))
    comparison=ComparisonProcess(directory,a.encoder_sign,a.vision_delay_ms,a.encoder_port)
    cam=Camera(a.camera,a.width,a.height,a.fps,a.rotate,a.exposure_raw,a.auto_exposure_raw,a.gain_raw)
    engine=Engine(a.fps,directory,a.detector_width,a.encoder_sign,a.vision_delay_ms,comparison);engine.camera=cam;stop=threading.Event()
    if a.calibration_file:engine.restore_calibration(a.calibration_file,a.width,a.height,a.rotate)
    recorder=BufferedRecorder(directory,a.fps) if a.record else None
    engine.recorder=recorder
    def worker():
        last=0;flushed=time.monotonic()
        try:
            with (directory/'states.jsonl').open('w') as log:
                while not stop.is_set():
                    item=cam.get()
                    if item is None or item[0]==last:stop.wait(.001);continue
                    seq,t,frame=item;last=seq
                    state=engine.process(frame,t,seq)
                    log.write(json.dumps(state,allow_nan=False)+'\n')
                    if recorder:recorder.write(frame,seq,t)
                    now=time.monotonic()
                    if now-flushed>1:log.flush();flushed=now
        except Exception as error:
            with engine.lock:engine.error=str(error)
            logging.exception('Tracking worker stopped')
        finally:
            if recorder:recorder.close()
    thread=threading.Thread(target=worker,name='vision-worker',daemon=True);thread.start()
    preview=PreviewWorker(engine,a.preview_fps)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server=None;started=time.monotonic()
    try:
        if not a.no_video:
            engine.video=VideoStream(cam,engine,a.width,a.height,a.video_fps,a.video_bitrate,a.gst_python)
        server=make_server('127.0.0.1',a.port,create_app(engine),threaded=True)
        server.timeout=.25
        print(f'Vision: http://127.0.0.1:{a.port} | requested {a.width}x{a.height} @ {a.fps} FPS | {directory}',flush=True)
        while a.duration is None or time.monotonic()-started<a.duration:
            server.handle_request()
            if engine.error:raise RuntimeError(engine.error)
    except KeyboardInterrupt:pass
    finally:
        stop.set();thread.join(timeout=5);preview.close()
        if engine.video is not None:engine.video.close()
        report=engine.snapshot()
        (directory/'final_report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
        engine.comparison.close()
        cam.close()
        if server is not None:server.server_close()
        print(json.dumps({'camera':report.get('camera'),'tracking':report.get('tracking'),
                          'processed_frames':report.get('processed_frames'),'skipped_camera_frames':report.get('skipped_camera_frames')},indent=2),flush=True)

if __name__=='__main__':main()
