"""Change one commissioning gain while stopped, recording native readbacks. Never enables motion."""
import argparse,json,math
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.rig import Rig

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--key',choices=('pz','pw','bw','ke','kpx','kdx','pc1','pc2','catch_v'),required=True);p.add_argument('--value',type=float,required=True);p.add_argument('--expected-reference',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if not math.isfinite(a.value):p.error('finite value required')
 a.output.mkdir(parents=True,exist_ok=False);report={'key':a.key,'requested':a.value}
 try:
  with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=a.output) as rig:
   try:
    report['before']=asdict(rig._stopped_healthy());report['info_before']=asdict(rig.get_info());report['parameters_before']=rig.get_parameters()
    if report['info_before']['encoder_upright_raw']!=a.expected_reference:raise RuntimeError('saved upright differs; no gain write')
    report['readback']=rig.set_parameter(a.key,a.value);report['parameters_after']=rig.get_parameters()
    if abs(report['parameters_after'][a.key]-a.value)>max(1e-6,abs(a.value)*1e-6):raise RuntimeError('gain readback mismatch')
   finally:
    rig.stop();report['after']=asdict(rig.state);report['info_after']=asdict(rig.get_info())
 except BaseException as error:report['error']=repr(error)
 (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report,indent=2));return int('error' in report)
if __name__=='__main__':raise SystemExit(main())
