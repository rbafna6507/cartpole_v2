"""Recover only diagnosed action expiry, preserving the existing counted home."""
import json,time,traceback
from pathlib import Path
from dataclasses import asdict
from cartpole_sdk.rig import Rig
p=Path('/home/rbafna/cartpole-v2-runs/python-id-20261016')/('expiry-rehome-'+str(time.time_ns()));p.mkdir();r={'case':'expiry-rehome'}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=p) as rig:
  try:
   rig.stop();info=rig.get_info();s=rig._snapshot(allow_error=True)
   r['before']=asdict(s);r['before_info']=asdict(info);print(json.dumps(r),flush=True)
   if info.firmware!='executor-v6-measuredrail' or info.encoder_upright_raw!=330:raise RuntimeError('unexpected firmware/reference')
   if s.enabled or not(s.flags&1) or not s.homed or not s.switch_profile or s.flags&48 or abs(s.x)>.27 or s.velocity!=0 or s.acceleration!=0:raise RuntimeError('requires healthy disabled stopped cart within guarded travel and released switches')
   if s.fault!=1:raise RuntimeError('only diagnosed action expiry may be cleared')
   rig.clear_fault();r['cleared']=asdict(rig._stopped_healthy())
   rig.rehome();deadline=time.monotonic()+16
   while rig.state.enabled:
    if time.monotonic()>deadline:raise TimeoutError('bounded rehome deadline')
    rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
   s=rig._stopped_healthy()
   if abs(s.x)>.001:raise RuntimeError('return did not reach counted home')
   r['return_completed']=True;r['final_info']=asdict(rig.get_info())
  except BaseException as e:r['failure']=repr(e);r['traceback']=traceback.format_exc();raise
  finally:
   rig.stop();r['stop_state']=asdict(rig.state);(p/'report.json').write_text(json.dumps(r,indent=2))
finally:print(json.dumps({'report':str(p/'report.json'),**r}),flush=True)
