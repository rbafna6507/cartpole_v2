import json,time
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
p=Path('runs/camera-id-20261021/clear-lease-01');p.mkdir(parents=True,exist_ok=False)
r={}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=p/'raw',vision_publisher=EncoderPublisher()) as rig:
  try:
   rig.stop();info=rig.get_info();s=rig.state
   r.update(info=asdict(info),before=asdict(s),parameters=rig.get_parameters())
   if info.encoder_upright_raw!=330 or info.home_epoch!=19 or s.fault!=1 or not s.flags&1 or s.enabled or s.mode!=4 or not s.homed or not s.switch_profile or s.flags&48 or abs(s.x)>.003:
    raise RuntimeError('Unexpected identity/state; leave fault latched')
   rig.clear_fault();rig.stop();r['after']=asdict(rig.state)
   assert rig.state.healthy and not rig.state.enabled
  finally:rig.stop()
finally:
 (p/'report.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r,indent=2))
