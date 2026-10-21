import json,time,urllib.request
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
out=Path('runs/camera-id-20261021/preflight-01');out.mkdir(parents=True,exist_ok=False)
def get():
 with urllib.request.urlopen('http://127.0.0.1:3090/api/state',timeout=1) as r:return json.load(r)
report={}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=out/'raw',vision_publisher=EncoderPublisher()) as rig:
  try:
   rig.stop();info=rig.get_info();params=rig.get_parameters();s=rig.state
   report.update(info=asdict(info),parameters=params,initial_state=asdict(s),camera_before=get())
   if s.enabled or s.mode or s.fault or not s.healthy or not s.switch_profile or not s.homed:
    raise RuntimeError('Need healthy stopped homed switch-protected rig')
   deadline=time.monotonic()+30;sample=[];done=False
   while time.monotonic()<deadline:
    s=rig.wait_state(after_tick=s.tick,timeout=.2);sample.append(asdict(s))
    if not s.healthy or s.enabled:raise RuntimeError('Rig state changed during stopped calibration')
    if len(sample)<200:continue
    if any(abs(z['theta'])<2.5 or abs(z['omega'])>.15 for z in sample[-200:]):continue
    cam=get()
    if cam.get('home_samples',0)<25:continue
    request=urllib.request.Request('http://127.0.0.1:3090/api/home',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
    try:
     with urllib.request.urlopen(request,timeout=2) as r:reply=json.load(r)
    except urllib.error.HTTPError as e:
     report.setdefault('camera_capture_refusals',[]).append(e.read().decode());continue
    report['camera_display_hanging_capture']=reply;done=True;break
   report['display_zero_captured']=done
   report['camera_after']=get()
   report['final_state']=asdict(rig.state)
  finally:rig.stop()
except BaseException as e:
 report['error']=str(e);raise
finally:
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if not k.startswith('camera_')},indent=2),flush=True)
