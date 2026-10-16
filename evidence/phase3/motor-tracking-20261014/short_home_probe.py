"""Single 0.5 s switch-protected slow motor probe; no automatic retry."""
from cartpole_sdk.rig import Rig
from dataclasses import asdict
from pathlib import Path
import time,json,traceback,urllib.request,threading,statistics
root=Path('/home/rbafna/cartpole-v2-runs')/('short-home-probe-'+str(time.time_ns()));root.mkdir()
report={'path':str(root),'duration_limit_s':.5,'nominal_velocity_m_s':-.03,'nominal_travel_m':.015,'states':[]}
stop=threading.Event();camera={'received':0.,'state':None,'last_detected':0.};cam_rows=[]
def camera_watch():
 while not stop.is_set():
  try:
   with urllib.request.urlopen('http://127.0.0.1:3090/api/state',timeout=.4) as response:d=json.load(response)
   now=time.monotonic();camera.update(received=now,state=d)
   if d.get('detected') and d.get('pivot_px') and d.get('confidence',0)>.5:
    camera['last_detected']=now;camera['last_point']=d['pivot_px']
   if not cam_rows or cam_rows[-1]['seq']!=d.get('seq'):cam_rows.append({k:d.get(k) for k in ('seq','t','pivot_px','confidence','detected','theta_rad')})
  except Exception as e:camera['error']=repr(e)
  stop.wait(.025)
def check_camera():
 d=camera['state'];assert d and time.monotonic()-camera['received']<.4 and d.get('age_since_host_read_s',1)<.15 and time.monotonic()-camera['last_detected']<.2,'camera unavailable'
threading.Thread(target=camera_watch,daemon=True).start()
try:
 time.sleep(.35);check_camera()
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,record_capacity=3000) as r:
  try:
   r.stop();info=r.get_info();before=r.state
   assert before.healthy and before.switch_profile and not before.enabled and not before.fault and ((before.flags>>4)&3)==0
   report['before']=asdict(before);report['info']=asdict(info)
   report['camera_before']=camera['last_point'];report['begin_host_s']=time.monotonic()
   r.home();start=time.monotonic();last=r.state.tick
   while time.monotonic()-start<.5:
    s=r.wait_state(after_tick=last,timeout=.1);last=s.tick;report['states'].append(asdict(s));check_camera()
    assert s.mode==13 and s.enabled and s.healthy and s.switch_profile and not s.fault and r.error is None
    assert s.misses==before.misses and abs(s.x-before.x)<.018
   r.stop();report['end_host_s']=time.monotonic();time.sleep(.3);check_camera()
   report['camera_after']=camera['last_point'];report['final']=asdict(r.state);report['final_info']=asdict(r.get_info())
   report['camera_delta_px']=[b-a for a,b in zip(report['camera_before'],report['camera_after'])]
   report['commanded_delta_m']=r.state.x-before.x;report['ok']=True
  finally:r.stop()
except BaseException as e:report.update(ok=False,error=repr(e),traceback=traceback.format_exc())
finally:
 stop.set();(root/'camera.json').write_text(json.dumps(cam_rows)+'\n');(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='states'},indent=2),flush=True)
if not report.get('ok'):raise SystemExit(1)
