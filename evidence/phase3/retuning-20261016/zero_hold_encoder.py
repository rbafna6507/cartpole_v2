"""Three bounded zero-command holds: isolate motor energizing from feedback motion.
Encoder-only motion guards; vision is an independent observation, never control.
"""
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from dataclasses import asdict
from pathlib import Path
import time,json,math,statistics,threading,urllib.request
root=Path('/home/rbafna/cartpole-v2-runs/retune-20261016')/('zero-command-repeats-'+str(time.time_ns()));root.mkdir(parents=True)
report={'path':str(root),'kind':'zero velocity enable comparison','states':[],'camera':[]};phase='initial';cycle=-1;end=threading.Event()
def watch():
 while not end.is_set():
  try:
   with urllib.request.urlopen('http://127.0.0.1:3090/api/state',timeout=.25) as response:d=json.load(response)
   report['camera'].append({'phase':phase,'cycle':cycle,'receipt_s':time.monotonic(),**d})
  except Exception as e:report['camera_error']=repr(e)
  end.wait(.04)
threading.Thread(target=watch,daemon=True).start()
def down(q):return math.atan2(math.sin(q-math.pi),math.cos(q-math.pi))
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,vision_publisher=EncoderPublisher()) as r:
  try:
   r.stop();info=r.get_info();report['initial_info']=asdict(info);initial=r.state
   assert info.encoder_upright_raw==330 and info.encoder_conf_valid,'reference/configuration changed'
   assert initial.homed and initial.healthy and initial.switch_profile and not initial.enabled and not initial.fault and abs(initial.x)<.001,'healthy stopped home required'
   for cycle in range(3):
    phase='settling';last=r.state.tick;window=[];started=time.monotonic()
    while time.monotonic()-started<30:
     s=r.wait_state(after_tick=last,timeout=.12);last=s.tick;now=time.monotonic()
     assert s.healthy and not s.enabled and not s.fault and s.homed and s.switch_profile and r.error is None,'settling health'
     assert abs(s.x)<.001 and abs(s.velocity)<1e-6,'settling cart moved'
     window.append((now,down(s.theta),abs(s.omega)));window=[p for p in window if p[0]>=now-1.02]
     if now-window[0][0]>=1 and max(q[2] for q in window)<.2 and max(q[1] for q in window)-min(q[1] for q in window)<.006 and abs(down(s.theta))<.3:break
    else:raise RuntimeError('pole did not settle')
    for phase,seconds in [('before',2.),('hold',2.),('after',3.)]:
     if phase=='hold':r.start('manual',3.);r.set_velocity(0.,50)
     elif phase=='after':r.stop()
     started=time.monotonic();renewed=started;last=r.state.tick
     while time.monotonic()-started<seconds:
      now=time.monotonic()
      if phase=='hold' and now-renewed>.012:r.set_velocity(0.,50);renewed=now
      s=r.wait_state(after_tick=last,timeout=.1);last=s.tick
      report['states'].append({'phase':phase,'cycle':cycle,**asdict(s)})
      assert s.healthy and s.homed and s.switch_profile and not s.fault and r.error is None,'health'
      assert s.misses==initial.misses,'control deadline miss'
      assert abs(s.x)<.001 and abs(s.velocity)<1e-6 and abs(s.acceleration)<1e-6,'unexpected commanded cart motion'
      assert s.enabled==(phase=='hold'),'unexpected enable state'
      assert abs(down(s.theta))<.3 and abs(s.omega)<10,'unexpected pole response'
    print(json.dumps({'completed_cycle':cycle+1,'x':r.state.x}),flush=True)
   report['ok']=True
  finally:
   r.stop();report['final']=asdict(r.state);report['final_info']=asdict(r.get_info())
except BaseException as e:report['ok']=False;report['error']=repr(e)
finally:
 end.set();summary=[]
 for cyc in range(3):
  phases={}
  for ph in ['before','hold','after']:
   rows=[s for s in report['states'] if s['cycle']==cyc and s['phase']==ph]
   if rows:
    angles=[math.degrees(down(s['theta'])) for s in rows]
    phases[ph]={'n':len(rows),'mean_down_deg':statistics.mean(angles),'std_deg':statistics.pstdev(angles),'range_deg':[min(angles),max(angles)],'max_abs_omega':max(abs(s['omega']) for s in rows)}
  if phases:summary.append({'cycle':cyc,**phases})
 report['summary']=summary;(root/'report.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k not in ('states','camera')},indent=2),flush=True)
if not report.get('ok'):raise SystemExit(1)
