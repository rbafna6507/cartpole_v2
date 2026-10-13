import json,time,pathlib,datetime,traceback,math
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.policy import run_policy,ZeroAccelerationPolicy
from cartpole_sdk.contracts import Channel
PORT='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
root=pathlib.Path.home()/'cartpole-v2-runs'/('executor-reference-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));root.mkdir(parents=True)
report={'path':str(root),'hex_sha256':'a53a2f2ab41661a090f36a479e7d68be6d9029d346b73fb54f61da6ad90da964','motor_power':'owner confirmed on after recovered stopped checks','center_basis':'owner originally centered; original measured return .00188m; fresh post-recovery camera confirms cart near midpoint; no independent metric cart measurement','reference_states':[],'return_states':[]}
try:
 with Rig(PORT,rate_hz=250,log_dir=root,record_capacity=8192) as rig:
  try:
   rig.stop();report['initial_info']=asdict(rig.get_info());report['initial']=asdict(rig.state)
   assert rig.state.healthy and not rig.state.enabled and rig.state.switch_profile
   assert report['initial_info']['encoder_upright_raw']==3485 and report['initial_info']['reference_saved']
   assert abs(rig.state.theta)>2.8 and abs(rig.state.omega)<.3,'pole not settled hanging'
   rig.configure_switches(False);rig.center()
   channels=(Channel('pole','angle','magnetic','encoder-zero'),Channel('cart','position','step','cart-step-home'))
   run_policy(rig,ZeroAccelerationPolicy,channels=channels,duration_s=.6,ttl_ms=20)
   report['powered_zero']=asdict(rig.state)
   assert abs(rig.state.x)<.001 and not rig.state.enabled and rig.state.fault==0
   rig.start('auto',10.5);began=time.monotonic();last=rig.state.tick;stop_reason='duration'
   while time.monotonic()-began<10:
    state=rig.wait_state(after_tick=last,timeout=.1);last=state.tick;report['reference_states'].append(asdict(state))
    if abs(state.x)>.205:stop_reason='position_guard';break
    if abs(state.omega)>30:stop_reason='angular_speed_guard';break
    if not state.enabled:raise RuntimeError('unexpected executor disable')
   rig.stop();report['reference_stop_reason']=stop_reason;report['reference_duration_s']=time.monotonic()-began;report['after_reference']=asdict(rig.state)
   rows=report['reference_states'];balance=[s for s in rows if s['mode']==3]
   report['reference_summary']={'samples':len(rows),'modes':sorted(set(s['mode'] for s in rows)),'max_abs_x':max(abs(s['x']) for s in rows),'balance_samples':len(balance),'balance_span_s':(balance[-1]['unwrapped_tick']-balance[0]['unwrapped_tick'])/1000 if balance else 0,'balance_angle_rms':math.sqrt(sum(s['theta']**2 for s in balance)/len(balance)) if balance else None}
   # Return only from a normal healthy run, never restart after a guard/fault.
   if stop_reason=='duration' and rig.state.healthy and rig.state.homed and abs(rig.state.x)>.008:
    sign=1 if rig.state.x>0 else -1;rig.start('manual',7);began=time.monotonic();braking=False
    while time.monotonic()-began<6.5:
     state=rig.state;report['return_states'].append(asdict(state))
     assert abs(state.x)<.23 and state.healthy
     if sign*state.x<.007:braking=True
     rig.set_velocity(0. if braking else -.04*sign,50)
     if braking and abs(state.velocity)<.001:break
     rig.wait_state(after_tick=state.tick,timeout=.1)
    else:raise RuntimeError('slow return timeout')
    rig.stop();report['after_return']=asdict(rig.state)
   report['ok']=stop_reason=='duration' and bool(balance)
  finally:
   rig.stop()
   if rig.error is not None:
    try:rig.clear_fault()
    except Exception as exc:report['restore_clear_error']=str(exc)
   try:rig.configure_switches(True)
   except Exception as exc:report['restore_switch_error']=str(exc)
   if rig.error is None:rig.set_rate(0)
   rig.stop();report['final']=asdict(rig.state);report['final_info']=asdict(rig.get_info())
except BaseException as exc:
 report['ok']=False;report['error']=repr(exc);report['traceback']=traceback.format_exc()
finally:
 (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 public={k:v for k,v in report.items() if not k.endswith('_states')};print(json.dumps(public,indent=2),flush=True)
if not report.get('ok'):raise SystemExit(1)
