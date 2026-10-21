"""Run normal numeric inference but send ZERO acceleration to isolate scheduling."""
import argparse,json,time,sys,threading
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.policy import run_policy
from cartpole_sdk.rig.runtime import defer_cyclic_gc
from cartpole_sdk.rig.transport import SerialTransport
from cartpole_sdk.contracts import Acceleration
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from cartpole_sdk.learning.balance_hardware import _load_policy
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--switch-ms',type=float,default=5.);p.add_argument('--duration',type=float,default=10.);p.add_argument('--clear-timeout',action='store_true');a=p.parse_args()
out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
r=dict(switch_ms=a.switch_ms,command='numeric compute, zero acceleration emission, bounded duration, 20 ms lease',success=False);writes=[];computes=[]
class InstrumentedTransport(SerialTransport):
 def write(self,data):
  w=time.monotonic_ns();c=time.thread_time_ns()
  try:return super().write(data)
  finally:writes.append((w,time.monotonic_ns(),time.thread_time_ns()-c,threading.current_thread().name,data.decode().strip()))
class ComputeZero:
 def __init__(self,actor):self.actor=actor;self.channels=actor.channels;self.fault_reason=None
 def reset(self,session):self.actor.reset(session)
 def act(self,observation):
  w=time.monotonic_ns();c=time.thread_time_ns()
  try:
   # Bypass only the balance-start pose in this zero-emission timing probe.
   # Actual actor observations, cadence and runtime rail/speed checks remain.
   self.actor._balance_started=True
   intent=self.actor.act(observation)
   self.fault_reason=self.actor.fault_reason
   return None if intent is None else Acceleration(0.)
  finally:computes.append((w,time.monotonic_ns(),time.thread_time_ns()-c))
old=sys.getswitchinterval()
try:
 sys.setswitchinterval(a.switch_ms/1000)
 policy=ComputeZero(_load_policy('training/candidates/balance-20261021-console/actor.json',guard_profile='rig',inference_backend='numpy'))
 with defer_cyclic_gc(),Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=100,log_dir=out,vision_publisher=EncoderPublisher(3096),transport_factory=InstrumentedTransport) as rig:
  try:
   r['before']=asdict(rig.state);r['info_before']=asdict(rig.get_info())
   if a.clear_timeout:
    assert rig.state.fault==1 and not rig.state.enabled and rig.state.flags&1 and not rig.state.flags&(16|32)
    rig.clear_fault();r['explicit_cleared_fault']=1
   rig._stopped_healthy();assert abs(rig.state.x)<.02 and abs(rig.state.velocity)<.001
   run_policy(rig,lambda c:policy,channels=policy.channels,observation_provider=rig.control_observation,duration_s=a.duration,max_acceleration=.1)
   r['success']=True
  except BaseException as e:r['error']=str(e);r['error_type']=type(e).__name__
  finally:
   rig.stop();r['after']=asdict(rig.state);r['info_after']=asdict(rig.get_info())
finally:
 sys.setswitchinterval(old);(out/'timings.json').write_text(json.dumps(dict(writes=writes,computes=computes))+'\n');(out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r))
