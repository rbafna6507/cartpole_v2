"""Recover one known isolated encoder latch after fresh stopped-health checks; home using physical switches."""
from pathlib import Path
from dataclasses import asdict
import json,time
from cartpole_sdk.rig import Rig
p=Path('runs/encoder-tuning-resume-20261021/recover-encoder-fault-kdx15-01');p.mkdir(parents=True,exist_ok=False);report={'samples':[]}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=p) as rig:
  try:
   rig.stop();before=rig.get_info();report['info_before']=asdict(before)
   if before.encoder_upright_raw!=533 or not before.encoder_conf_valid:raise RuntimeError('unexpected encoder configuration')
   start=time.monotonic()
   while time.monotonic()-start<10:
    s=rig._snapshot(allow_error=True);i=rig.get_info();report['samples'].append({'state':asdict(s),'info':asdict(i)})
    if s.enabled or s.fault not in (0,4) or not (s.flags&1) or not s.switch_profile:raise RuntimeError('not eligible to clear isolated encoder fault')
    if i.i2c_errors!=before.i2c_errors or i.encoder_recoveries!=before.encoder_recoveries:raise RuntimeError('encoder errors still increasing')
    time.sleep(.1)
   rig.clear_fault();report['after_clear']=asdict(rig._stopped_healthy());rig.home();deadline=time.monotonic()+90
   while rig.state.enabled or rig.state.mode:
    rig._require();rig._fresh(rig.state)
    if time.monotonic()>deadline:raise RuntimeError('HOME timeout')
    rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
   if not rig.state.homed or rig.state.x!=0 or not rig.state.healthy:raise RuntimeError('HOME did not finish healthy at center')
   report['success']=True
  finally:
   rig.stop();report['after']=asdict(rig.state);report['info_after']=asdict(rig.get_info())
except BaseException as error:report['error']=repr(error)
(p/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2));raise SystemExit(int('error' in report))
