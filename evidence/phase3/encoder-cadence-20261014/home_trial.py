from cartpole_sdk.rig import Rig
from dataclasses import asdict
from pathlib import Path
import time,json,traceback,urllib.request,threading
root=Path('/home/rbafna/cartpole-v2-runs')/('encoder-home-'+str(time.time_ns()));root.mkdir()
report={'path':str(root),'switches':'required left/right, enabled','motor_power':'on, owner confirmed'}
stop=threading.Event();camera={'received':0.,'state':None,'error':None}
def camera_watch():
 while not stop.is_set():
  try:
   with urllib.request.urlopen('http://127.0.0.1:3090/api/state',timeout=.5) as response:d=json.load(response)
   camera.update(received=time.monotonic(),state=d,error=None)
  except Exception as e:camera['error']=repr(e)
  stop.wait(.1)
def camera_check():
 d=camera['state'];assert d and time.monotonic()-camera['received']<.75 and (d.get('age_since_host_read_s') or 0)<.3 and not d.get('stale'), 'camera not fresh'
t=threading.Thread(target=camera_watch,daemon=True);t.start()
try:
 time.sleep(.3);camera_check()
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,record_capacity=20000) as r:
  try:
   r.stop();info=r.get_info();before=r.state;report['info']=asdict(info);report['before']=asdict(before)
   assert info.firmware=='executor-v3-encguard' and info.encoder_conf_valid
   assert before.switch_profile and before.healthy and not before.enabled and not before.fault
   assert ((before.flags>>4)&3)==0
   r.home();begin=time.monotonic();last=0;seen=set()
   while time.monotonic()-begin<58:
    s=r.wait_state(after_tick=last,timeout=.15);last=s.tick;camera_check()
    assert s.healthy and s.switch_profile and not s.fault and r.error is None
    assert s.misses==before.misses,'missed control deadline'
    seen.add((s.flags>>4)&3)
    if not s.enabled:
     assert s.homed and s.mode==0,'homing stopped without success';break
   else:raise RuntimeError('host homing time bound')
   r.stop();report['duration_s']=time.monotonic()-begin;report['contacts_seen']=sorted(seen)
   report['after']=asdict(r.state);report['final_info']=asdict(r.get_info())
   assert report['final_info']['measured_span_steps']>=10667
   assert report['final_info']['i2c_errors']==info.i2c_errors
   report['ok']=True
  finally:
   r.stop();report['final']=asdict(r.state);report['final_info']=asdict(r.get_info())
except BaseException as e:
 report['ok']=False;report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
 stop.set();report['camera']={k:camera['state'].get(k) for k in ['seq','age_since_host_read_s','status']} if camera['state'] else camera
 (root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
if not report.get('ok'):raise SystemExit(1)
