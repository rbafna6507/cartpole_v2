from cartpole_sdk.rig import Rig
from pathlib import Path
from dataclasses import asdict
import time,json
root=Path('/home/rbafna/cartpole-v2-runs/retune-20261016')/('recovered-encoder-check-'+str(time.time_ns()));root.mkdir(parents=True)
report={'path':str(root),'states':[]}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=root,record_capacity=2048) as r:
  try:
   r.stop();info=r.get_info();report['before_info']=asdict(info);report['before']=asdict(r.state)
   assert r.state.fault==4 and not r.state.enabled,'only stopped encoder fault expected'
   assert info.encoder_conf_valid and info.encoder_upright_raw==330,'encoder configuration changed'
   start=time.monotonic();last=r.state.tick
   while time.monotonic()-start<2:
    s=r._wait_state(after_tick=last,timeout=.1,allow_error=True);last=s.tick
    assert s.flags&1 and s.switch_profile and ((s.flags>>4)&3)==0 and not s.enabled,'raw sensor health/switch state'
    report['states'].append(asdict(s))
   after=r.get_info();assert after.i2c_errors==info.i2c_errors and after.encoder_conf_valid and after.encoder_raw_age_us<5000,'encoder not consistently recovered'
   r.clear_fault();report['after']=asdict(r.state);assert r.state.healthy and not r.state.fault and not r.state.enabled,'clear failed'
   report['ok']=True
  finally:r.stop();report['final']=asdict(r.state);report['final_info']=asdict(r.get_info())
except Exception as e:report['ok']=False;report['error']=repr(e)
finally:
 (root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='states'},indent=2))
if not report.get('ok'):raise SystemExit(1)
