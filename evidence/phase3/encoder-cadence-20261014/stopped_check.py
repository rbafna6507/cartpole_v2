from dataclasses import asdict
from pathlib import Path
from collections import Counter
import json,time,statistics,traceback
from cartpole_sdk.rig import Rig
out=Path('/home/rbafna/cartpole-v2-runs/encoder-check-20261014');out.mkdir(exist_ok=True)
report={'motor_power':'off, owner confirmed','motion_commands':False}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=1000,log_dir=out,record_capacity=12000) as r:
  r.stop();time.sleep(.1);before=r.state;report['before']=asdict(before);report['info']=asdict(r.get_info())
  assert report['info']['firmware']=='executor-v3-encguard'
  assert report['info']['encoder_upright_raw']==270 and report['info']['reference_saved']
  assert report['info']['encoder_conf_valid']
  assert before.healthy and not before.enabled and not before.homed and before.switch_profile
  t=time.monotonic()
  while time.monotonic()-t<4:
   assert r.error is None and r.state.healthy and not r.state.enabled
   time.sleep(.01)
  r.stop();report['after']=asdict(r.state);report['final_info']=asdict(r.get_info())
  rows=[s['state'] for s in r.records if s['type']=='state' and s['state']['tick']>=before.tick]
  changes=[];previous=rows[0]
  for s in rows[1:]:
   if s['theta']!=previous['theta']:changes.append(s['tick']-previous['tick']);previous=s
  report['samples']=len(rows);report['change_intervals_ticks']=Counter(changes).most_common(20)
  report['change_interval_median']=statistics.median(changes) if changes else None
  report['deadline_misses_delta']=r.state.misses-before.misses
  report['i2c_errors_delta']=report['final_info']['i2c_errors']-report['info']['i2c_errors']
  assert report['deadline_misses_delta']==0 and report['i2c_errors_delta']==0
  r.set_rate(100)
 report['ok']=True
except BaseException as e:
 report['ok']=False;report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
 (out/'stopped-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
if not report['ok']:raise SystemExit(1)
