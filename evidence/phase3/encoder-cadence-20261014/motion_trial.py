from cartpole_sdk.rig import Rig
from dataclasses import asdict
from pathlib import Path
from collections import Counter
import time,json,traceback,urllib.request,threading,sys,math,statistics
kind=sys.argv[1];assert kind in ('manual','auto')
duration=float(sys.argv[2]) if len(sys.argv)>2 else (2.5 if kind=='manual' else 5.)
assert 0<duration<=12
root=Path('/home/rbafna/cartpole-v2-runs')/('encoder-'+kind+'-'+str(time.time_ns()));root.mkdir()
report={'path':str(root),'kind':kind,'requested_s':duration,'gains':'unchanged saved controller','states':[]}
stop=threading.Event();camera={'received':0.,'state':None,'error':None};cam_rows=[]
def camera_watch():
 last=None
 while not stop.is_set():
  try:
   with urllib.request.urlopen('http://127.0.0.1:3090/api/state',timeout=.4) as response:d=json.load(response)
   camera.update(received=time.monotonic(),state=d,error=None)
   if d.get('seq')!=last:
    last=d.get('seq');cam_rows.append({'host_s':time.monotonic(),**{k:d.get(k) for k in ['seq','t','theta_rad','omega_rad_s','pivot_px','bob_px','confidence','detected','age_since_host_read_s']}})
  except Exception as e:camera['error']=repr(e)
  stop.wait(.03)
def camera_check():
 d=camera['state'];assert d and time.monotonic()-camera['received']<.75 and isinstance(d.get('age_since_host_read_s'),(int,float)) and d['age_since_host_read_s']<.3 and not d.get('stale'), 'camera not fresh'
threading.Thread(target=camera_watch,daemon=True).start()
try:
 time.sleep(.3);camera_check()
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,record_capacity=12000) as r:
  try:
   r.stop();info=r.get_info();before=r.state;report['info']=asdict(info);report['before']=asdict(before)
   assert info.firmware=='executor-v3-encguard' and info.encoder_conf_valid and info.measured_span_steps>=10667
   assert before.switch_profile and before.healthy and before.homed and not before.enabled and not before.fault
   assert abs(before.x)<.06 and abs(before.omega)<.3 and abs(before.theta)>2.8,'not near center and settled hanging'
   limit=min(info.rail_half_m-.04,.205) if kind=='auto' else .08
   r.start(kind,duration+.5);begin=time.monotonic();last=r.state.tick
   if kind=='manual':r.set_velocity(0,50)
   while time.monotonic()-begin<duration:
    s=r.state;elapsed=time.monotonic()-begin
    if kind=='manual':
     target=0. if elapsed<.4 else .05 if elapsed<1.1 else 0. if elapsed<1.4 else -.05 if elapsed<2.1 else 0.
     r.set_velocity(target,50)
    s=r.wait_state(after_tick=last,timeout=.1);last=s.tick;report['states'].append(asdict(s));camera_check()
    assert s.healthy and s.switch_profile and s.homed and s.enabled and not s.fault and r.error is None
    assert s.misses==before.misses,'missed control deadline'
    assert abs(s.x)<limit, 'host position guard'
    assert abs(s.omega)<30,'host angular speed guard'
   r.stop();report['duration_s']=time.monotonic()-begin
   rows=report['states'];bal=[s for s in rows if s['mode']==3]
   periods=[];prev=rows[0]
   for s in rows[1:]:
    if s['theta']!=prev['theta']:periods.append(s['tick']-prev['tick']);prev=s
   report['summary']={'samples':len(rows),'modes':dict(Counter(s['mode'] for s in rows)),'max_abs_x':max(abs(s['x']) for s in rows),'max_abs_velocity':max(abs(s['velocity']) for s in rows),'max_abs_omega':max(abs(s['omega']) for s in rows),'angle_change_intervals_ticks':Counter(periods).most_common(10),'median_change_ticks':statistics.median(periods) if periods else None,'balance_s':len(bal)/250,'balance_angle_rms':math.sqrt(sum(s['theta']**2 for s in bal)/len(bal)) if bal else None}
   report['ok']=True
  finally:
   r.stop();report['final']=asdict(r.state);report['final_info']=asdict(r.get_info())
except BaseException as e:
 report['ok']=False;report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
 stop.set();(root/'camera.json').write_text(json.dumps(cam_rows))
 (root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='states'},indent=2),flush=True)
if not report.get('ok'):raise SystemExit(1)
