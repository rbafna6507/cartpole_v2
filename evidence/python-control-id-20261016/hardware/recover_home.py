import json,time,traceback
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
root=Path('/home/rbafna/cartpole-v2-runs/python-id-20261016');d=root/('physical-home-'+str(time.time_ns()));d.mkdir();r={}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=d,record_capacity=2048,vision_publisher=EncoderPublisher()) as rig:
  try:
   r['info_before']=asdict(rig.get_info());r['parameters']=rig.get_parameters();r['before']=asdict(rig.state)
   s=rig.state
   if s.enabled or not s.switch_profile or s.flags&48:raise RuntimeError('requires disabled driver and released installed switches')
   if s.fault or rig.error:rig.clear_fault()
   rig.home();deadline=time.monotonic()+120;next_print=0
   while rig.state.enabled:
    s=rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
    if time.monotonic()>deadline:raise TimeoutError('homing did not finish')
    if time.monotonic()>next_print:print(json.dumps(dict(mode=s.mode,flags=s.flags,x=s.x,v=s.velocity,fault=s.fault)),flush=True);next_print=time.monotonic()+10
   if not(rig.state.healthy and rig.state.homed and abs(rig.state.x)<.001):raise RuntimeError('home not verified')
   r['after']=asdict(rig.state);r['info_after']=asdict(rig.get_info());print(json.dumps(r['info_after']),flush=True)
  except BaseException as e:r['failure']=repr(e);r['traceback']=traceback.format_exc();raise
  finally:
   rig.stop();r['stopped']=asdict(rig.state);(d/'home-report.json').write_text(json.dumps(r,indent=2))
finally:print(json.dumps(dict(path=str(d),failure=r.get('failure'))),flush=True)
