from pathlib import Path
from dataclasses import asdict
import time,json,statistics
from cartpole_sdk.rig import Rig
from cartpole_sdk.identification.experiments import CameraRecorder
from cartpole_sdk.sensing.telemetry import EncoderPublisher
def main():
 p=Path('runs/encoder-tightening-20261021/upright-check-03');p.mkdir(exist_ok=False,parents=True)
 camera=CameraRecorder('http://127.0.0.1:3090/api/sensing-stream?max_hz=100',p,40.)
 report={'purpose':'user-supported natural upright pose, user ready and clear; no motion or calibration writes','samples':[]}
 try:
  camera.start()
  with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=p,vision_publisher=EncoderPublisher(3096)) as rig:
   try:
    report['before']=asdict(rig._stopped_healthy());report['info_before']=asdict(rig.get_info())
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
     rig._require();rig._fresh(rig.state);camera.check()
     s=rig.state
     if s.enabled or s.mode or not s.healthy or s.fault:raise RuntimeError('not healthy disabled')
     report['samples'].append({'host_monotonic_ns':time.monotonic_ns(),'state':asdict(s),'info':asdict(rig.get_info())})
     time.sleep(.25)
   finally:
    rig.stop();report['after']=asdict(rig.state);report['info_after']=asdict(rig.get_info())
 except BaseException as e:report['error']=repr(e)
 finally:
  report['camera']=camera.close();(p/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'directory':str(p),'error':report.get('error'),'raw_counts':[s['info']['encoder_raw'] for s in report['samples']],'theta':[s['state']['theta'] for s in report['samples']],'after':report.get('after'),'info_after':report.get('info_after'),'camera_frames':report['camera'].get('frames')}))

if __name__=="__main__":main()
