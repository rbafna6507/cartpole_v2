#!/usr/bin/env python3
"""Extract a lightweight, non-fit preview from a preserved column export.

Run: extract_passive_preview.py columns.json.gz --output NEW.json.gz
This is a strided visual aid for selecting release intervals before scoring.
The original full-resolution raw recording remains the fitting source.
"""
import argparse,gzip,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True)
p.add_argument('--stride',type=int,default=10)
a=p.parse_args()
if a.output.exists():raise ValueError('output exists')
if a.stride<1:raise ValueError('positive stride required')
b=a.input.read_bytes();d=json.loads(gzip.decompress(b));s=d['states'];sc=d['state_columns'];vc=d['vision_columns']
si=[sc.index(k) for k in ('unwrapped_us','received_ns','theta','flags','fault','mode')]
vi=[vc.index(k) for k in ('t','image_angle_rad','pivot_px','confidence','detected')]
o=dict(schema='cartpole-passive-preview-v1',not_for_fitting=True,stride=a.stride,
 source_export_sha256=hashlib.sha256(b).hexdigest(),source_hashes=d['source_hashes'],
 report=d['report'],state_count=len(s),state_columns=[sc[i] for i in si],
 states=[[r[i] for i in si] for r in s[::a.stride]],
 vision_columns=[vc[i] for i in vi],vision=[[r[i] for i in vi] for r in d['vision'][::3]])
a.output.write_bytes(gzip.compress(json.dumps(o,separators=(',',':'),allow_nan=False).encode(),mtime=0))
print(json.dumps(dict(output=str(a.output),bytes=a.output.stat().st_size,state_count=len(s),preview_states=len(o['states']))))
