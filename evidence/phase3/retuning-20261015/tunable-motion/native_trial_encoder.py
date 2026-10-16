"""Bounded operator experiments, with an independent camera freshness guard."""
from dataclasses import asdict
from pathlib import Path
from collections import Counter
import argparse,json,time,math,threading,urllib.request,traceback
from cartpole_sdk.rig import Rig
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from cartpole_sdk.sensing.stream import SensingStreamClient, StreamDeadline

p=argparse.ArgumentParser()
p.add_argument('kind',choices=['home','manual','auto','return','rehome','inspect'])
p.add_argument('--seconds',type=float,default=8.)
p.add_argument('--params',default='{}')
p.add_argument('--name',default='trial')
p.add_argument('--speed',type=float,default=.045)
p.add_argument('--expected-reference',type=int)
p.add_argument('--encoder-only',action='store_true',help='Use firmware encoder/switch safety; camera is observation-only')
a=p.parse_args()
assert 0<a.seconds<=30
assert 0<abs(a.speed)<=.12
changes=json.loads(a.params);assert isinstance(changes,dict)
root=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')/(a.name+'-'+str(time.time_ns()));root.mkdir(parents=True)
report={'path':str(root),'kind':a.kind,'requested_s':a.seconds,'changes':changes,'states':[],'vision_guard_enabled':not a.encoder_only,'control_source':'magnetic encoder'}
end=threading.Event();camera={};cam_rows=[]
def watch():
 deadline=time.monotonic()+90.;after=None;session=None
 while not end.is_set():
  try:
   client=SensingStreamClient('http://127.0.0.1:3090/api/sensing-stream',timeout_s=.4)
   for env,received in client.messages(deadline=deadline,after_seq=after,session=session,max_hz=100):
    if end.is_set():return
    d=env['vision'];enc=env['encoder'];now=time.monotonic()
    if enc.get('latest_seq') is not None:after=enc['latest_seq'];session=enc.get('session')
    camera.update(state=d,received=now)
    if d.get('angle_valid') and d.get('pivot_px') and d.get('confidence',0)>.5:
     camera['last_valid']=(now,d);camera['detected_at']=now
    if not cam_rows or cam_rows[-1]['seq']!=d.get('seq'):
     cam_rows.append({'receipt_s':received/1e9,**d})
   return
  except StreamDeadline:camera['error']='absolute camera recorder deadline';return
  except Exception as e:camera['error']=repr(e);end.wait(.05)
def camera_check(strict=True):
 if a.encoder_only:return
 d=camera.get('state');now=time.monotonic()
 fresh=bool(d and now-camera['received']<.6 and isinstance(d.get('age_since_host_read_s'),(float,int)) and d['age_since_host_read_s']<.3 and not d.get('stale'))
 if not fresh:
  report['camera_guard_failure']={'host_now_s':now,'last_receipt_s':camera.get('received'),'stream_error':camera.get('error'),'snapshot':d}
 assert fresh,'camera stale'
 # A fast pole can briefly hide its marker; bound loss explicitly during auto.
 assert now-camera.get('detected_at',0)<(.5 if strict else 2.),'camera lost cart/pole'
 if d.get('detected'):
  x,y=d['pivot_px'];assert 180<x<880 and 160<y<290,'cart outside visible rail guard'
def camera_pose():
 camera_check()
 if a.encoder_only and ('last_valid' not in camera or time.monotonic()-camera['last_valid'][0]>=.5):return None
 captured,d=camera['last_valid']
 if not a.encoder_only:assert time.monotonic()-captured<.5,'camera pose stale'
 return {'pivot_px':list(d['pivot_px']),'seq':d.get('seq'),'received_s':captured}
def snap(name):
 try:
  with urllib.request.urlopen('http://127.0.0.1:3090/preview.jpg',timeout=.8) as response:(root/name).write_bytes(response.read())
 except Exception as e:report['snapshot_error']=str(e)
threading.Thread(target=watch,daemon=True).start()
try:
 camera_deadline=time.monotonic()+3
 while True:
  try:camera_check();break
  except AssertionError:
   if time.monotonic()>=camera_deadline:raise
   time.sleep(.05)
 snap('before.jpg')
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,record_capacity=40000,vision_publisher=EncoderPublisher()) as r:
  try:
   r.stop();info=r.get_info();before=r.state;report['info']=asdict(info);report['before']=asdict(before)
   report['parameters_before']=r.get_parameters()
   if a.expected_reference is not None:assert info.encoder_upright_raw==a.expected_reference,'encoder reference changed'
   assert info.encoder_conf_valid and before.healthy and before.switch_profile and not before.enabled and not before.fault,'initial board health'
   assert ((before.flags>>4)&3)==0,'cart switch open'
   for k,v in changes.items():r.set_parameter(k,v)
   report['parameters']=r.get_parameters();report['profile']=r.save_parameters(root/'parameters.json')
   info=r.get_info();report['applied_info']=asdict(info)
   normal_margin=report['parameters'].get('rail_margin',.015)
   fault_margin=report['parameters'].get('rail_fault_margin',.010)
   assert normal_margin>fault_margin>0,'invalid software rail margins'
   host_margin=min(.0025,(normal_margin-fault_margin)/2)
   host_position_bound=info.rail_half_m-fault_margin-host_margin
   report['host_position_bound_m']=host_position_bound
   assert host_position_bound>0,'invalid measured position guard'
   for key,value in changes.items():
    assert math.isclose(report['parameters'][key],value,rel_tol=2e-6,abs_tol=2e-7),'parameter readback mismatch'
   if a.kind=='auto':
    # Repeated trials start at the same saved center with one continuous second
    # of low angular speed and a narrow raw-angle range. Never clear faults.
    settle_started=time.monotonic();window=[];last_settle=r.state.tick
    while time.monotonic()-settle_started<25:
     s=r.wait_state(after_tick=last_settle,timeout=.15);last_settle=s.tick;camera_check()
     assert s.healthy and s.switch_profile and s.homed and not s.enabled and not s.fault and r.error is None,'settling health'
     assert abs(s.x)<.0015 and abs(s.velocity)<.001,'settling center'
     now=time.monotonic();angle=math.atan2(math.sin(s.theta-math.pi),math.cos(s.theta-math.pi))
     window.append((now,angle,abs(s.omega)));window=[q for q in window if q[0]>=now-1.02]
     if window[-1][0]-window[0][0]>=1 and max(q[2] for q in window)<.3 and max(q[1] for q in window)-min(q[1] for q in window)<.012 and abs(angle)<.30:
      report['settling']={'seconds':now-settle_started,'angle_range_rad':max(q[1] for q in window)-min(q[1] for q in window),'max_abs_omega':max(q[2] for q in window),'mean_down_angle':sum(q[1] for q in window)/len(window)}
      before=s;report['motion_start']=asdict(s);report['camera_start_pose']=camera_pose();report['camera_start']=report['camera_start_pose']['pivot_px'] if report['camera_start_pose'] else None;break
    else:raise RuntimeError('settling criterion not reached within 25 seconds')
   if a.kind=='inspect':report['ok']=True
   else:
    if a.kind=='home':r.home();duration=74.
    elif a.kind=='rehome':r.rehome();duration=15.1
    else:
     assert before.homed and info.measured_span_steps>=10667,'physical home required'
     assert abs(before.x)<info.rail_half_m-normal_margin,'starting position near rail'
     assert abs(before.omega)<.5 and abs(before.theta)>2.75,'pole not settled hanging'
     if a.kind in ('manual','auto'):assert abs(before.x)<.025,'start near center'
     duration=a.seconds
     r.start('auto' if a.kind=='auto' else 'manual',duration if a.kind=='auto' else duration+.75)
     if a.kind=='auto':duration+=15.1
     if a.kind!='auto':r.set_velocity(0,50)
    started=time.monotonic();last=r.state.tick;last_print=-1;stalled=[]
    while time.monotonic()-started<duration:
     elapsed=time.monotonic()-started
     if a.kind in ('manual','return'):
      s=r.state
      if a.kind=='manual':target=a.speed if .25<elapsed<.85 else -a.speed if 1.5<elapsed<2.1 else 0.
      else:
       # Gentle proportional return with a deceleration window and small deadband.
       target=max(-.045,min(.045,-1.5*s.x)) if abs(s.x)>.001 else 0.
      r.set_velocity(target,50)
     s=r.wait_state(after_tick=last,timeout=.12);last=s.tick;report['states'].append(asdict(s));camera_check(strict=a.kind!='auto')
     assert s.healthy and s.switch_profile and not s.fault and r.error is None,'board health or switch fault'
     assert s.misses==before.misses,'control deadline miss'
     if a.kind=='home':
      if not s.enabled:
       assert s.homed and s.mode==0,'home stopped without success';break
      d=camera.get('state',{})
      if not a.encoder_only and d.get('detected'):
       stalled.append((elapsed,s.x,d['pivot_px'][0]))
       stalled=[q for q in stalled if q[0]>elapsed-1.]
       if len(stalled)>10 and stalled[-1][0]-stalled[0][0]>.7 and abs(s.x-stalled[0][1])>.02:
        assert abs(d['pivot_px'][0]-stalled[0][2])>6,'camera observes stalled motor'
     else:
      if a.kind in ('auto','rehome') and not s.enabled:
       assert s.homed and s.mode==0 and s.x==0,'return ended away from saved home';break
      assert s.homed and s.enabled,'unexpected motion end'
      assert abs(s.x)<host_position_bound,'host position guard'
      assert abs(s.omega)<30,'angular speed guard'
      if a.kind=='return' and elapsed>.3 and abs(s.x)<.0015 and abs(s.velocity)<.001:break
     if int(elapsed//5)>last_print:
      last_print=int(elapsed//5);print(json.dumps({'progress_s':round(elapsed,2),'mode':s.mode,'x':s.x,'theta':s.theta,'omega':s.omega}),flush=True)
    else:
     if a.kind in ('home','return','auto','rehome'):raise RuntimeError('motion completion timeout')
    r.stop();report['duration_s']=time.monotonic()-started;report['ok']=True
    # Capture free decay without motion after the excitation/run.
    if a.kind in ('manual','auto'):
     started_rest=time.monotonic()
     while time.monotonic()-started_rest<4:
      s=r.wait_state(after_tick=last,timeout=.15);last=s.tick;report['states'].append(asdict(s));camera_check(strict=False)
   report['final']=asdict(r.state);report['final_info']=asdict(r.get_info())
   if a.kind=='auto' and report.get('ok'):
    report['camera_end_pose']=camera_pose();report['camera_end']=report['camera_end_pose']['pivot_px'] if report['camera_end_pose'] else None
    if report.get('camera_start') and report.get('camera_end'):
     delta=report['camera_end'][0]-report['camera_start'][0];report['camera_return_delta_px']=delta
     if not a.encoder_only:assert abs(delta)<5,'camera return displacement exceeds 5 pixels'
  finally:
   r.stop();report['final']=asdict(r.state)
   if a.kind=='auto' and not report.get('ok') and not r.state.enabled:
    rest_start=time.monotonic();rest_tick=r.state.tick
    while time.monotonic()-rest_start<4:
     s=r._wait_state(after_tick=rest_tick,timeout=.2,allow_error=True);rest_tick=s.tick
     report['states'].append(asdict(s))
   try:report['final_info']=asdict(r.get_info())
   except Exception as e:report['final_info_error']=str(e)
   report['records_dropped']=r.records_dropped
except BaseException as e:
 report['ok']=False;report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
 end.set();snap('after.jpg')
 rows=report['states'];bal=[s for s in rows if s['mode']==3]
 if rows:report['summary']={'samples':len(rows),'modes':dict(Counter(s['mode'] for s in rows)),'max_abs_x':max(abs(s['x']) for s in rows),'max_abs_v':max(abs(s['velocity']) for s in rows),'max_abs_omega':max(abs(s['omega']) for s in rows),'mode3_sample_duration_lower_bound_s':max(0,(len(bal)-1))*.004,'balance_angle_rms':math.sqrt(sum(s['theta']**2 for s in bal)/len(bal)) if bal else None}
 (root/'camera.json').write_text(json.dumps(cam_rows))
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:report[k] for k in ('path','kind','changes','duration_s','ok','error','summary','final','final_info','records_dropped','settling','camera_return_delta_px') if k in report},indent=2),flush=True)
if not report.get('ok'):raise SystemExit(1)
