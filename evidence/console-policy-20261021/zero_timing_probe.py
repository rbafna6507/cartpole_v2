import argparse,json,time,sys
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.policy import run_policy,ZeroAccelerationPolicy
from cartpole_sdk.rig.runtime import defer_cyclic_gc
from cartpole_sdk.contracts import Channel
from cartpole_sdk.sensing.telemetry import EncoderPublisher
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--switch-ms',type=float,default=5.);p.add_argument('--clear-timeout',action='store_true');a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
r=dict(switch_ms=a.switch_ms,command='zero acceleration, 5 s, 20 ms lease',success=False)
old=sys.getswitchinterval()
try:
 sys.setswitchinterval(a.switch_ms/1000)
 with defer_cyclic_gc(),Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=out,vision_publisher=EncoderPublisher(3096)) as rig:
  try:
   r['before']=asdict(rig.state);r['info_before']=asdict(rig.get_info())
   if a.clear_timeout:
    assert rig.state.fault==1 and not rig.state.enabled and rig.state.flags&1 and not rig.state.flags&(16|32)
    rig.clear_fault();r['explicit_cleared_fault']=1
   rig._stopped_healthy();assert abs(rig.state.x)<.02 and abs(rig.state.velocity)<.001
   channels=(Channel('pole','angle','magnetic','encoder-zero'),Channel('cart','position','step','cart-step-home'))
   run_policy(rig,lambda c:ZeroAccelerationPolicy(c),channels=channels,duration_s=5.,max_acceleration=.1)
   r['success']=True
  except BaseException as e:r['error']=str(e);r['error_type']=type(e).__name__
  finally:
   rig.stop();r['after']=asdict(rig.state);r['info_after']=asdict(rig.get_info())
finally:
 sys.setswitchinterval(old);(out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r))
