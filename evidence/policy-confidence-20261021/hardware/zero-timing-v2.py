#!/usr/bin/env python3
"""Research timing probe: run the validated actor, emit only zero acceleration.

Requires sibling timing_instrumentation.py. Optional logger/mirror switches do
not alter actor computation,100Hz cadence,20ms leases or hardware parameters.
"""
import argparse,json,sys,traceback
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from timing_instrumentation import (TimingRecorder,InstrumentedTransport,InstrumentedRig,
                                    instrument_actor,runtime_metadata)
from cartpole_sdk.rig.policy import run_policy
from cartpole_sdk.rig.runtime import defer_cyclic_gc
from cartpole_sdk.contracts import Acceleration
from cartpole_sdk.sensing.telemetry import EncoderPublisher
from cartpole_sdk.learning.balance_hardware import _load_policy
LEASE_MS=20

def parse_args(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--out',required=True,type=Path);p.add_argument('--switch-ms',type=float,choices=(1.,5.),default=5.)
 p.add_argument('--duration',type=float,default=10.);p.add_argument('--clear-timeout',action='store_true')
 p.add_argument('--no-mirror',action='store_true');p.add_argument('--no-logger',action='store_true')
 p.add_argument('--actor',type=Path,default=Path('training/candidates/balance-20261021-confidence/actor.json'))
 p.add_argument('--port',default='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00')
 a=p.parse_args(argv)
 if not .01<=a.duration<=60:p.error('duration must be finite and within .01..60 seconds')
 return a

class ComputeZero:
 def __init__(self,actor):self.actor=actor;self.channels=actor.channels;self.fault_reason=None
 def reset(self,session):self.actor.reset(session)
 def act(self,observation):
  # Identical to the prior zero probe: bypass only initial upright pose for a
  # zero-emission scheduling experiment. Runtime reference/rail/speed checks run.
  self.actor._balance_started=True
  intent=self.actor.act(observation);self.fault_reason=self.actor.fault_reason
  return None if intent is None else Acceleration(0.)

def main(argv=None):
 a=parse_args(argv);a.out.mkdir(parents=True,exist_ok=False);timings=TimingRecorder();timings._buffer();rig=None
 r=dict(switch_ms=a.switch_ms,duration_s=a.duration,lease_ms=LEASE_MS,command='validated numeric actor with zero acceleration emission',success=False,
  hardware_accepted=False,driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
  instrumentation_sha256=sha256(Path(__file__).with_name('timing_instrumentation.py').read_bytes()).hexdigest(),
  actor=str(a.actor),actor_file_sha256=sha256(a.actor.read_bytes()).hexdigest(),
  diagnostic_workers=dict(mirror_enabled=not a.no_mirror,logger_enabled=not a.no_logger,record_capacity=100000))
 old=sys.getswitchinterval();sys.setswitchinterval(a.switch_ms/1000)
 try:
  policy=ComputeZero(_load_policy(a.actor,guard_profile='rig',inference_backend='numpy'))
  with instrument_actor(timings),defer_cyclic_gc(),InstrumentedRig(a.port,timings=timings,rate_hz=100,log_dir=None if a.no_logger else a.out,
    record_capacity=100000,vision_publisher=None if a.no_mirror else EncoderPublisher(3096),
    transport_factory=lambda port:InstrumentedTransport(port,timings=timings)) as rig:
   try:
    r['runtime_environment']=runtime_metadata();r['before']=asdict(rig.state);r['info_before']=asdict(rig.get_info())
    if a.clear_timeout:
     assert rig.state.fault==1 and not rig.state.enabled and rig.state.flags&1 and not rig.state.flags&(16|32)
     rig.clear_fault();r['explicit_cleared_fault']=1
    rig._stopped_healthy();assert abs(rig.state.x)<.02 and abs(rig.state.velocity)<.001
    run_policy(rig,lambda c:policy,channels=policy.channels,observation_provider=rig.control_observation,
               duration_s=a.duration,max_acceleration=.1,ttl_ms=LEASE_MS)
    r['success']=True
   finally:
    rig.stop();r['after']=asdict(rig.state);r['info_after']=asdict(rig.get_info())
 except BaseException as e:r['error']=str(e);r['error_type']=type(e).__name__;traceback.print_exc()
 finally:
  r['runtime_environment_after']=runtime_metadata();sys.setswitchinterval(old)
  if a.no_logger and rig is not None:
   saved=tuple(rig.records)  # Rig.close and deferred-GC scope have exited first.
   r['memory_records']=len(saved);r['memory_capacity_exhausted']=len(saved)==rig.records.maxlen
   (a.out/f'rig-memory-{rig.session.session_id}.jsonl').write_text(''.join(json.dumps(v,allow_nan=False)+'\n' for v in saved))
  (a.out/'timings.json').write_text(json.dumps(timings.snapshot(),allow_nan=False)+'\n')
  (a.out/'report.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');print(json.dumps(r,indent=2))
 return int(not r['success'])

if __name__=='__main__':sys.exit(main())
