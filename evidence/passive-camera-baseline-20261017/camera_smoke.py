"""Read-only camera path check; never opens Rig/serial."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from cartpole_sdk.identification.experiments import CameraRecorder
from cartpole_sdk.identification.passive_baseline import camera_geometry


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    recorder=CameraRecorder('http://127.0.0.1:3090/api/sensing-stream?max_hz=100',a.output,10.)
    seen=set();valid=0;total=0
    try:
        recorder.start();deadline=time.monotonic()+5.
        while time.monotonic()<deadline:
            recorder.check();row=recorder.latest()
            if row:
                key=(row['vision']['seq'],row['vision']['t'])
                if key not in seen:
                    seen.add(key);total+=1;valid+=camera_geometry(row['vision']) is not None
            time.sleep(.01)
    finally:report=recorder.close()
    result=dict(camera_report=report,preview_samples=total,valid_geometry_samples=valid,
                geometry_fraction=valid/total if total else 0,serial_opened=False,motion_commanded=False)
    (a.output/'smoke-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    if report.get('failure'):raise SystemExit(2)


if __name__=='__main__':main()
