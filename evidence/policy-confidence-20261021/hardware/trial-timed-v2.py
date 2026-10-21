#!/usr/bin/env python3
"""Research instrumentation of one bounded actual console-policy trial (up to60s).

Requires sibling timing_instrumentation.py; original trial-timed.py is unchanged.

Run on the Jetson with the console closed. Readback/calibration require disabled
hardware. Rehome/run are explicit operations; no fallback or automatic clearing.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import traceback
import threading
from timing_instrumentation import (TimingRecorder,InstrumentedTransport,InstrumentedRig,
                                    instrument_actor,runtime_metadata)
from cartpole_sdk.rig.console_policy import ConsolePolicy
from cartpole_sdk.rig.runtime import defer_cyclic_gc
from cartpole_sdk.sensing.telemetry import EncoderPublisher


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('inspect','upright','rehome','shadow','run'))
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--actor',type=Path)
    p.add_argument('--reference',type=int)
    p.add_argument('--duration',type=float,default=1.)
    p.add_argument('--switch-ms',type=float,choices=(1.,5.),default=5.)
    p.add_argument('--no-mirror',action='store_true',help='Disable optional encoder display publisher')
    p.add_argument('--no-logger',action='store_true',help='Retain Rig records in memory and serialize only after STOP/close')
    p.add_argument('--port',default='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00')
    a=p.parse_args(argv)
    if a.operation in ('shadow','run') and (a.actor is None or a.reference is None):p.error('policy invocation requires actor and expected saved reference')
    if not .01<=a.duration<=60:p.error('this research driver accepts .01..60 seconds')
    return a


def main(argv=None):
    a=parse_args(argv);timings=TimingRecorder();timings._buffer()
    a.out.mkdir(parents=True,exist_ok=False)
    report={'operation':a.operation,'duration_s':a.duration,'success':False,'hardware_accepted':False,
            'driver_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'instrumentation_sha256':sha256(Path(__file__).with_name('timing_instrumentation.py').read_bytes()).hexdigest(),
            'gil_switch_interval_ms':a.switch_ms,
            'success_semantics':'operation completed; assess balance separately from the trace'}
    if a.actor:report.update(actor=str(a.actor),actor_file_sha256=sha256(a.actor.read_bytes()).hexdigest())
    report['diagnostic_workers']=dict(mirror_enabled=not a.no_mirror,logger_enabled=not a.no_logger,record_capacity=100000)
    rig=None
    original_switch=sys.getswitchinterval();sys.setswitchinterval(a.switch_ms/1000)
    try:
        with instrument_actor(timings),defer_cyclic_gc(),InstrumentedRig(a.port,timings=timings,rate_hz=250,log_dir=None if a.no_logger else a.out,record_capacity=100000,vision_publisher=None if a.no_mirror else EncoderPublisher(3096),transport_factory=lambda port:InstrumentedTransport(port,timings=timings)) as rig:
            try:
                report['runtime_environment']=runtime_metadata()
                rig.stop();report['before_info']=asdict(rig.get_info());report['before_state']=asdict(rig._stopped_healthy())
                report['parameters']=rig.get_parameters()
                if a.reference is not None and report['before_info']['encoder_upright_raw']!=a.reference:raise RuntimeError('saved reference changed')
                if a.operation=='upright':
                    report['calibration']=asdict(rig.calibrate_encoder('upright'))
                elif a.operation=='rehome':
                    rig.rehome();deadline=time.monotonic()+16
                    while rig.state.enabled or rig.state.mode:
                        rig._require();rig._fresh(rig.state)
                        if time.monotonic()>deadline:raise TimeoutError('REHOME deadline exceeded')
                        rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
                    if not rig.state.homed or rig.state.x!=0:raise RuntimeError('REHOME did not return to counted center')
                elif a.operation in ('shadow','run'):
                    policy=ConsolePolicy();policy.load(rig,a.actor);report['check']=policy.check(rig)
                    report['result']=policy.run(rig,execute=a.operation=='run',duration_s=a.duration,output=sys.stdout)
                else:time.sleep(1)
                report['success']=True
            finally:
                rig.stop();time.sleep(.08)
                report['after_state']=asdict(rig.state)
                report['after_info']=asdict(rig.get_info())
    except BaseException as error:
        report['success']=False;report['error']=str(error);report['error_type']=type(error).__name__;traceback.print_exc()
    finally:
        report['runtime_environment_after']=runtime_metadata()
        sys.setswitchinterval(original_switch)
        if a.no_logger and rig is not None:
            saved=tuple(rig.records)  # All context managers, including Rig.close, have exited.
            report['memory_records']=len(saved);report['memory_capacity_exhausted']=len(saved)==rig.records.maxlen
            (a.out/f'rig-memory-{rig.session.session_id}.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in saved))
        (a.out/'timings.json').write_text(json.dumps(timings.snapshot(),allow_nan=False)+'\n')
        (a.out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps(report,indent=2))
    return int(not report['success'])

if __name__=='__main__':sys.exit(main())
