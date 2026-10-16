from cartpole_sdk.rig import Rig
from cartpole_sdk.control import ControllerParameters
from cartpole_sdk.rig.parameters import float32
from dataclasses import asdict
from pathlib import Path
import json,time,traceback
out=Path('/home/rbafna/cartpole-v2-runs/parameters-check-20261014');out.mkdir(exist_ok=True)
report={'motor_power':'off, owner confirmed','motion_commands':False}
try:
 with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=out,record_capacity=4000) as r:
  try:
   r.stop();info=r.get_info();before=r.state;report['info']=asdict(info);report['before']=asdict(before)
   assert info.encoder_upright_raw==270 and info.reference_saved and info.encoder_conf_valid
   assert before.healthy and before.switch_profile and not before.enabled and not before.homed and not before.fault
   params=r.get_parameters();report['parameters']=params
   for k,v in asdict(ControllerParameters()).items():assert float32(params[k])==float32(v),(k,v,params[k])
   r.save_parameters(out/'working-defaults.json')
   assert r.set_parameter('jmax',75)==75
   assert r.get_parameter('jmax')==75
   r.load_parameters(out/'working-defaults.json')
   assert r.get_parameter('jmax')==150
   t=time.monotonic()
   while time.monotonic()-t<2:
    assert r.state.healthy and not r.state.enabled and r.error is None
    time.sleep(.01)
   assert all(not (rec['state']['flags']&2) for rec in r.records if rec['type']=='state')
   report['after']=asdict(r.state);report['final_info']=asdict(r.get_info());report['final_parameters']=r.get_parameters()
   assert report['final_info']['i2c_errors']==info.i2c_errors==0
   assert report['after']['misses']==before.misses==0
   r.set_rate(100);report['ok']=True
  finally:r.stop()
except BaseException as e:
 report['ok']=False;report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
if not report.get('ok'):raise SystemExit(1)
