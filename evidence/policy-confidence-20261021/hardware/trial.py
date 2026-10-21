#!/usr/bin/env python3
"""One bounded hardware trial through the actual console policy implementation.

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
from cartpole_sdk.rig import Rig
from cartpole_sdk.rig.console_policy import ConsolePolicy
from cartpole_sdk.rig.runtime import defer_cyclic_gc
from cartpole_sdk.sensing.telemetry import EncoderPublisher


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('inspect','upright','rehome','shadow','run'))
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--actor',type=Path)
    p.add_argument('--reference',type=int)
    p.add_argument('--duration',type=float,default=1.)
    p.add_argument('--port',default='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00')
    a=p.parse_args()
    if a.operation in ('shadow','run') and (a.actor is None or a.reference is None):p.error('policy invocation requires actor and expected saved reference')
    if not .01<=a.duration<=10:p.error('this quick-trial driver accepts .01..10 seconds')
    a.out.mkdir(parents=True,exist_ok=False)
    report={'operation':a.operation,'duration_s':a.duration,'success':False,'hardware_accepted':False,
            'driver_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'success_semantics':'operation completed; assess balance separately from the trace'}
    if a.actor:report.update(actor=str(a.actor),actor_file_sha256=sha256(a.actor.read_bytes()).hexdigest())
    try:
        with defer_cyclic_gc(),Rig(a.port,rate_hz=250,log_dir=a.out,vision_publisher=EncoderPublisher(3096)) as rig:
            try:
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
        (a.out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps(report,indent=2))
    return int(not report['success'])

if __name__=='__main__':sys.exit(main())
