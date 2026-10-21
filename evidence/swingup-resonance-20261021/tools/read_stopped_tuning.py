"""Stopped readback only. Does not clear faults, rehome, enable, or write parameters."""
from dataclasses import asdict
from pathlib import Path
import json
from cartpole_sdk.rig import Rig
out=Path('runs/encoder-tuning-resume-20261021/stopped-readback-01');out.mkdir(parents=True,exist_ok=False)
with Rig('/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00',rate_hz=250,log_dir=out) as rig:
 rig.stop();s=rig._snapshot(allow_error=True)
 if s.enabled:raise RuntimeError('Expected motor disabled')
 r={'state':asdict(s),'info':asdict(rig.get_info()),'parameters':rig.get_parameters(),'motion_started':False};rig.stop()
(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
