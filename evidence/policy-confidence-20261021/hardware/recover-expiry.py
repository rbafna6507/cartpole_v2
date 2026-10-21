"""Explicitly clear one diagnosed action-expiry latch, then counted rehome."""
from dataclasses import asdict
from pathlib import Path
import json,time
from cartpole_sdk.rig import Rig
import argparse
a=argparse.ArgumentParser();a.add_argument('--out',required=True);a.add_argument('--reference',type=int,required=True);a=a.parse_args()
p=Path(a.out);p.mkdir(parents=True,exist_ok=False)
r={}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=p) as rig:
  try:
   rig.stop();before=rig.get_info();r['before_info']=asdict(before);r['before_state']=asdict(rig.state)
   if before.encoder_upright_raw!=a.reference or not before.encoder_conf_valid:raise RuntimeError('unexpected reference/configuration')
   for _ in range(10):
    s=rig._snapshot(allow_error=True);info=rig.get_info()
    if s.enabled or s.fault!=1 or not s.homed or not s.switch_profile or not s.flags&1 or s.flags&48:raise RuntimeError('not an isolated stopped expiry')
    if info.i2c_errors!=before.i2c_errors:raise RuntimeError('encoder error count increased')
    time.sleep(.1)
   rig.clear_fault();rig.rehome();deadline=time.monotonic()+16
   while rig.state.enabled or rig.state.mode:
    rig._require();rig._fresh(rig.state)
    if time.monotonic()>deadline:raise TimeoutError('rehome deadline')
    rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
   if rig.state.x!=0:raise RuntimeError('not at counted center')
   r['success']=True
  finally:
   rig.stop();r['after_state']=asdict(rig.state);r['after_info']=asdict(rig.get_info())
except BaseException as e:r['error']=repr(e);r['success']=False
(p/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
raise SystemExit(int(not r['success']))
