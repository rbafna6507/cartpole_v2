from pathlib import Path
from dataclasses import asdict
import time,json
from cartpole_sdk.rig import Rig
from cartpole_sdk.identification.experiments import CameraRecorder
from cartpole_sdk.sensing.telemetry import EncoderPublisher

def main():
 out=Path('runs/encoder-tightening-20261021/ref533-bw8-bal10-01');out.mkdir(exist_ok=False,parents=True)
 report={'requested_duration_s':10,'command':'bal','user_clear':True,'success':False}
 camera=CameraRecorder('http://127.0.0.1:3090/api/sensing-stream?max_hz=100',out,50.)
 try:
  camera.start()
  with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=out,vision_publisher=EncoderPublisher(3096)) as rig:
   try:
    report['before']=asdict(rig._stopped_healthy());report['info_before']=asdict(rig.get_info());report['parameters']=rig.get_parameters()
    s=rig.state
    if report['info_before']['encoder_upright_raw']!=533 or abs(s.theta)>.04 or abs(s.omega)>.15 or abs(s.x)>.005 or not s.homed or not s.switch_profile:raise RuntimeError('upright/center/reference/profile preflight failed')
    report['start_ns']=time.monotonic_ns();rig._record('balance_check_start');rig.start('bal',10)
    deadline=time.monotonic()+25.25
    while rig.state.enabled or rig.state.mode:
     rig._require();rig._fresh(rig.state);camera.check()
     if not rig.state.healthy or rig.state.fault:raise RuntimeError('board fault or health loss')
     if time.monotonic()>deadline:raise TimeoutError('native BAL/return deadline')
     rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
    rig._require();rig._fresh(rig.state)
    if not rig.state.homed or abs(rig.state.x)>.00005 or not rig.state.healthy:raise RuntimeError('completion not home/healthy')
    report['end_ns']=time.monotonic_ns();report['success']=True
   except BaseException as e:report['error']=repr(e)
   finally:
    rig.stop();report['after']=asdict(rig.state);report['info_after']=asdict(rig.get_info())
  report['records_dropped']=rig.records_dropped
 except BaseException as e:report['error']=repr(e);report['success']=False
 finally:
  report['camera']=camera.close();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report))
if __name__=='__main__':main()
