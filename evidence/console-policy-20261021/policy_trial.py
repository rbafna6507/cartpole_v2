"""One explicit stopped/shadow/learned run, preserving a complete JSONL trace."""
import argparse, json, time, traceback
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.console_policy import ConsolePolicy
from cartpole_sdk.rig.runtime import defer_cyclic_gc
from cartpole_sdk.sensing.telemetry import EncoderPublisher
p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--duration',type=float,default=1.);p.add_argument('--reference',type=int,default=371);p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
report={'execute':a.execute,'requested_duration_s':a.duration,'actor':'training/candidates/balance-20261021-console/actor.json'}
try:
 with defer_cyclic_gc(), Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=out,vision_publisher=EncoderPublisher(3096)) as rig:
  try:
   report['before_info']=asdict(rig.get_info());report['before_state']=asdict(rig._stopped_healthy())
   assert report['before_info']['encoder_upright_raw']==a.reference,'reference unexpectedly changed'
   policy=ConsolePolicy();policy.load(rig,report['actor'])
   report['check']=policy.check(rig)
   report['result']=policy.run(rig,execute=a.execute,duration_s=a.duration,output=__import__('sys').stdout)
   report['success']=True
  except BaseException as e:
   report['success']=False;report['error']=str(e);report['error_type']=type(e).__name__;traceback.print_exc()
  finally:
   rig.stop();time.sleep(.05)
   report['after_state']=asdict(rig.state)
   try:report['after_info']=asdict(rig.get_info())
   except Exception as e:report['after_info_error']=str(e)
finally:
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
