#!/usr/bin/env python3
"""Inspect the live board while disabled; never arm or command motion."""
import argparse,json,time
from dataclasses import asdict
from pathlib import Path
from cartpole_sdk.rig import Rig
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',default='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00')
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
report={}
with Rig(a.port,rate_hz=100,log_dir=a.output,record_capacity=4096) as rig:
    rig.stop()
    report['initial_state']=asdict(rig.state)
    report['info']=asdict(rig.get_info())
    report['parameters']=rig.get_parameters()
    states=[];end=time.monotonic()+1.0;s=rig.state
    while time.monotonic()<end:
        s=rig.wait_state(after_tick=s.unwrapped_tick,timeout=.1)
        if s.enabled:raise RuntimeError('driver must remain disabled')
        states.append(asdict(s))
    rig.stop();report['final_state']=asdict(rig.state)
    report['states']=states
    report['log']=str(rig.log_path)
    report['records_dropped']=rig.records_dropped
(a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='states'},indent=2))
