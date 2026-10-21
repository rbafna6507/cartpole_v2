import json
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
p=Path('runs/camera-id-20261021/bw8-preparation');p.mkdir(parents=True,exist_ok=False)
r={}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=p/'raw',vision_publisher=EncoderPublisher()) as rig:
  try:
   rig.stop();info=rig.get_info();before=rig.get_parameters();s=rig.state
   r.update(info=asdict(info),before=before,state=asdict(s))
   if info.encoder_upright_raw!=330 or info.home_epoch!=19 or not s.healthy or s.enabled or s.mode!=0 or not s.homed or not s.switch_profile or s.flags&48 or abs(s.x)>.003:
    raise RuntimeError('Unexpected stopped rig identity/state')
   rig.set_parameter('bw',8.)
   after=rig.get_parameters();r['after']=after
   assert all(after[k]==(8. if k=='bw' else v) for k,v in before.items())
  finally:rig.stop()
finally:
 (p/'report.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'info':r.get('info'),'changes':{k:[v,r['after'][k]] for k,v in r.get('before',{}).items() if 'after' in r and v!=r['after'][k]}},indent=2))
