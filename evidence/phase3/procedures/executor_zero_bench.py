"""Motor supply OFF. Zero-demand lease and default-interlock tests only."""
import json,time,pathlib,datetime,traceback
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.client import RigError
PORT='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
root=pathlib.Path.home()/'cartpole-v2-runs'/('executor-zero-bench-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));root.mkdir(parents=True)
report={'path':str(root),'motor_supply':'off, confirmed by owner','scope':'board logic and live serial only, no physical motion acceptance'}
try:
 with Rig(PORT,rate_hz=250,log_dir=root,record_capacity=8192) as rig:
  report['info']=asdict(rig.get_info());rig.stop()
  rig.configure_switches(False);rig.center()
  report['temporary_origin']='bench-only test origin while motor power off, invalidated before return'
  rig.arm(1.5);count=0;began=time.monotonic();first=rig.state
  while time.monotonic()-began<1:
   rig.set_acceleration(0.,20);count+=1
   rig.wait_state(after_tick=rig.state.tick,timeout=.1)
  rig.stop();report['zero_policy']={'sent':count,'duration_s':time.monotonic()-began,'before':asdict(first),'after':asdict(rig.state),'error':None if rig.error is None else str(rig.error)}
  assert not rig.state.enabled and rig.state.fault==0 and abs(rig.state.x)<1e-9
  rig.arm(1.);seq=rig.set_acceleration(0.,20);observed=rig.state.tick;began=time.monotonic()
  while time.monotonic()-began<.3 and rig.state.fault==0:time.sleep(.002)
  report['expiry']={'last_sequence':seq,'tick_before_send':observed,'elapsed_host_s':time.monotonic()-began,'state':asdict(rig.state),'sdk_error':str(rig.error)}
  assert rig.state.fault==1 and not rig.state.enabled,'action lease failed to expire'
  rig.stop();rig.clear_fault();rig.configure_switches(True)
  assert not rig.state.homed and not rig.state.enabled and rig.state.switch_profile
  rig.set_rate(0);rig.stop();report['final']=asdict(rig.state);report['final_info']=asdict(rig.get_info())
 with Rig(PORT,rate_hz=100,log_dir=root) as rig:
  try:rig._command('HOME')
  except RigError as exc:
   report['home_rejection']=str(exc)
   assert 'executor rejected HOME' in str(exc)
  else:raise AssertionError('HOME accepted with all switch circuits open')
  finally:rig.stop()
 # Fresh session after deliberate rejection; never clear or arm implicitly.
 with Rig(PORT,rate_hz=0,log_dir=root) as rig:
  report['final']=asdict(rig.state);assert not rig.state.enabled and not rig.state.homed and rig.state.switch_profile and rig.state.fault==0
 report['ok']=True
except BaseException as exc:
 report['ok']=False;report['error']=repr(exc);report['traceback']=traceback.format_exc()
finally:
 (root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
if not report['ok']:raise SystemExit(1)
