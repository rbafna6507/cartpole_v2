#!/usr/bin/env python3
"""Record camera/encoder agreement before and after one bounded native AUTO trial.

Run from a release with: uv run --locked --extra hardware python THIS_SCRIPT
--help. Never calibrates, clears faults, flashes, or changes gains by default.
"""
import argparse
import hashlib
from collections import deque
from dataclasses import asdict
import json
import math
from pathlib import Path
import time


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',default='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--duration',type=float,default=25.)
    p.add_argument('--execute',action='store_true',help='run native AUTO; otherwise stopped recording only')
    p.add_argument('--home',action='store_true',help='seek both switches before AUTO; requires --execute')
    p.add_argument('--bw',type=float,choices=(6.,8.,10.),help='optional temporary observer bandwidth, restored afterward')
    p.add_argument('--expected-reference',type=int,required=True)
    p.add_argument('--camera-url',default='http://127.0.0.1:3090/api/sensing-stream?max_hz=100')
    a=p.parse_args(argv)
    if not math.isfinite(a.duration) or not 1 <= a.duration <= 25:p.error('duration must be within 1..25 seconds')
    if (a.home or a.bw is not None) and not a.execute:p.error('--home/--bw require --execute')
    if not 0 <= a.expected_reference < 4096:p.error('reference must be in 0..4095')
    from cartpole_sdk.rig import Rig
    from cartpole_sdk.identification.experiments import CameraRecorder
    from cartpole_sdk.sensing.telemetry import EncoderPublisher
    from cartpole_sdk.rig.runtime import defer_cyclic_gc
    a.output.mkdir(parents=True,exist_ok=False)
    report=dict(schema='post-fixture-encoder-check-v1',requested_duration_s=a.duration,execute=a.execute,
                expected_reference=a.expected_reference,success=False,events=[],physical_balance_accepted=False,
                collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    camera=CameraRecorder(a.camera_url,a.output,240.)
    def mark(rig,name,**details):
        row=dict(event=name,host_monotonic_ns=time.monotonic_ns(),**details)
        report['events'].append(row);rig._record('encoder_check_phase',event=name,**details)
        print(json.dumps(row),flush=True)
    def check(rig):
        rig._require();rig._fresh(rig.state);camera.check()
        if rig.state.fault:raise RuntimeError('executor fault '+str(rig.state.fault))
        if not rig.state.healthy:raise RuntimeError('unhealthy encoder state')
    def pin(rig):
        info=rig.get_info()
        if info.encoder_upright_raw!=a.expected_reference or not info.reference_saved:
            raise RuntimeError('saved upright reference changed; no calibration attempted')
        if info.encoder_conf_valid is not True:raise RuntimeError('invalid encoder configuration')
        return asdict(info)
    def record_rest(rig,label):
        mark(rig,label+'_settling')
        window=deque();deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            check(rig);s=rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1);check(rig)
            if s.enabled or s.mode:raise RuntimeError('not disabled during resting measurement')
            if abs(s.omega)>.15 or abs(s.theta)<2.5:window.clear()
            else:window.append(s)
            if window and s.received_ns-window[0].received_ns>=2_000_000_000:break
        else:raise RuntimeError('pole did not settle hanging within 40 seconds')
        mark(rig,label+'_start',info=pin(rig))
        deadline=time.monotonic()+5;next_info=0
        while time.monotonic()<deadline:
            check(rig)
            s=rig.state
            if s.enabled or s.mode:raise RuntimeError('unexpected motion enable/mode during rest')
            if abs(s.omega)>.15 or abs(s.theta)<2.5:raise RuntimeError('pole moved during declared rest window')
            if time.monotonic()>=next_info:
                pin(rig);next_info=time.monotonic()+.25
            rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
        check(rig);s=rig.state
        if s.enabled or s.mode or abs(s.omega)>.15 or abs(s.theta)<2.5:
            raise RuntimeError('pole moved or enabled at end of declared rest window')
        mark(rig,label+'_end',info=pin(rig))
    def wait_disabled(rig,seconds):
        deadline=time.monotonic()+seconds
        while rig.state.enabled or rig.state.mode:
            check(rig)
            if time.monotonic()>deadline:raise TimeoutError('native motion did not finish within deadline')
            rig.wait_state(after_tick=rig.state.unwrapped_tick,timeout=.1)
        check(rig)
        if not rig.state.homed or rig.state.x!=0:raise RuntimeError('native completion did not confirm counted home')
    bw_attempted=False;original_bw=None
    try:
        camera.start()
        with defer_cyclic_gc(),Rig(a.port,rate_hz=250,log_dir=a.output,vision_publisher=EncoderPublisher(3096)) as rig:
            try:
                report['before']=asdict(rig._stopped_healthy());report['info_before']=pin(rig)
                report['parameters_before']=rig.get_parameters();original_bw=report['parameters_before']['bw']
                if not rig.state.switch_profile:raise RuntimeError('enabled cart switch profile required')
                record_rest(rig,'initial_rest')
                if a.execute:
                    mark(rig,'home_start',full_home=a.home)
                    if a.home:rig.home()
                    else:rig.rehome()
                    wait_disabled(rig,90 if a.home else 15.25)
                    mark(rig,'home_end',info=pin(rig))
                    record_rest(rig,'before_auto_rest')
                    if a.bw is not None:
                        bw_attempted=True;rig.set_parameter('bw',a.bw)
                    report['test_parameters']=rig.get_parameters()
                    mark(rig,'auto_start',duration_s=a.duration)
                    auto_began=time.monotonic()
                    rig.start('auto',a.duration);wait_disabled(rig,a.duration+15.25)
                    if time.monotonic()-auto_began<a.duration-.05:
                        raise RuntimeError('native AUTO disabled before requested duration elapsed')
                    mark(rig,'auto_and_return_end',info=pin(rig))
                    record_rest(rig,'after_auto_rest')
                report['success']=True
            except BaseException as error:
                report['error']=repr(error)
                print(json.dumps(dict(error=repr(error))),flush=True)
            finally:
                try:rig.stop()
                except BaseException as error:report['stop_error']=repr(error);report['success']=False
                if bw_attempted:
                    try:report['bw_restored']=rig.set_parameter('bw',original_bw)
                    except BaseException as error:report['restore_error']=repr(error);report['success']=False
                report['after']=asdict(rig.state)
                try:report['info_after']=pin(rig);report['parameters_after']=rig.get_parameters()
                except BaseException as error:report['final_readback_error']=repr(error);report['success']=False
        report['records_dropped']=rig.records_dropped
        report['rig_error_after_close']=None if rig.error is None else repr(rig.error)
        if rig.records_dropped or rig.error is not None:
            report['success']=False;report['log_failure']='rig/log error or dropped records after close'
    except BaseException as error:
        report['error']=repr(error);report['success']=False
    finally:
        try:report['camera']=camera.close()
        except BaseException as error:report['camera']={'failure':'camera close failed: '+repr(error)}
        if report['camera'].get('failure'):report['success']=False
        (a.output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('events','parameters_before','parameters_after','test_parameters')}),flush=True)
    return 0 if report['success'] else 1

if __name__=='__main__':raise SystemExit(main())
