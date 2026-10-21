import json,time,urllib.request
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
p=Path('runs/camera-id-20261021/handoff');p.mkdir(parents=True,exist_ok=False)
saved=json.loads(Path('runs/camera-id-20261021/bw8-preparation/report.json').read_text())['before'];r={}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=p/'raw',vision_publisher=EncoderPublisher()) as rig:
  try:
   rig.stop();info=rig.get_info();before=rig.get_parameters();s=rig.state
   r.update(info=asdict(info),before=before,initial_state=asdict(s))
   if info.encoder_upright_raw!=330 or info.home_epoch!=19 or not s.healthy or s.enabled or s.mode!=0 or not s.homed or not s.switch_profile or s.flags&48 or abs(s.x)>.003:
    raise RuntimeError('Unexpected stopped rig identity/state; no parameter change')
   assert all(v==before[k] for k,v in saved.items() if k!='bw')
   rig.set_parameter('bw',saved['bw']);after=rig.get_parameters();r['after']=after
   assert after==saved
   deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    s=rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.2)
    if s.enabled or not s.healthy:raise RuntimeError('State changed during disabled telemetry check')
   with urllib.request.urlopen('http://127.0.0.1:3090/api/state?history=1&history_limit=30',timeout=3) as response:r['viewer']=json.load(response)
   r['mirror_error']=rig.vision_telemetry_error
   rig.stop();r['final_state']=asdict(rig.state)
  finally:rig.stop()
finally:
 (p/'report.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:v for k,v in r.items() if k not in ('viewer','before','after')},indent=2))
 print(json.dumps({'parameters_restored':r.get('after')==saved,'camera_angle_valid':r.get('viewer',{}).get('angle_valid'),'comparison':r.get('viewer',{}).get('comparison',{}).get('status')},indent=2))
