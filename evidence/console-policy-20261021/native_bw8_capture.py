import json,time
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from cartpole_sdk.identification.experiments import CameraRecorder,DEFAULT_CAMERA_URL
from cartpole_sdk.rig.runtime import defer_cyclic_gc

def wait_disabled(rig,timeout):
 deadline=time.monotonic()+timeout
 while rig.state.enabled:
  rig._require()
  if time.monotonic()>deadline:raise TimeoutError('native completion deadline')
  rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
 assert rig.state.fault==0 and rig.state.x==0

def main():
 out=Path('runs/console-policy-20261021/native-baseline-bw8-25s-01');out.mkdir(parents=True,exist_ok=False)
 report={'controller':'preserved native AUTO','duration_s':25.,'success':False};camera=CameraRecorder(DEFAULT_CAMERA_URL,out,55)
 try:
  camera.start()
  with defer_cyclic_gc(),Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=out,vision_publisher=EncoderPublisher(3096)) as rig:
   try:
    report['before']=asdict(rig._stopped_healthy());report['info_before']=asdict(rig.get_info());report['parameters']=rig.get_parameters()
    rig.rehome();wait_disabled(rig,15.25);time.sleep(2)
    rig.set_parameter('bw',8.);report['test_bw']=8.;rig._record('baseline_auto_start');rig.start('auto',25.);wait_disabled(rig,40.25);report['success']=True
   except BaseException as e:report['error']=str(e)
   finally:rig.stop();report['restored_bw']=rig.set_parameter('bw',10.);report['after']=asdict(rig.state);report['info_after']=asdict(rig.get_info())
 finally:
  report['camera']=camera.close();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report))
if __name__=='__main__':main()
