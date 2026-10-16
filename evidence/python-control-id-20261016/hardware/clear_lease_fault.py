import json,time
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
p=Path('/home/rbafna/cartpole-v2-runs/python-id-20261016')/('lease-recovery-'+str(time.time_ns()));p.mkdir();r={}
with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=p) as rig:
 try:
  rig.stop();s=rig.state;r['before']=asdict(s);r['before_info']=asdict(rig.get_info())
  if s.enabled or not (s.flags&1) or not s.homed or not s.switch_profile or s.flags&48 or abs(s.x)>.003:raise RuntimeError('requires disabled healthy home with released switches')
  if s.fault!=1:raise RuntimeError('expected only diagnosed action expiry fault')
  rig.clear_fault();r['after']=asdict(rig.state)
 finally:
  rig.stop();r['stop_state']=asdict(rig.state);(p/'report.json').write_text(json.dumps(r,indent=2))
print(json.dumps(r))
