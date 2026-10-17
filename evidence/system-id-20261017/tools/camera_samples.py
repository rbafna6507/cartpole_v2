#!/usr/bin/env python3
"""Save a short raw camera diagnostic; state brackets are not exact frame matches."""
import argparse,json,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--url',default='http://127.0.0.1:3090');p.add_argument('--count',type=int,default=12);a=p.parse_args()
if not 1<=a.count<=30:raise ValueError('count must be 1..30')
a.output.mkdir(parents=True,exist_ok=False)
for i in range(a.count):
    def read(path):
        with urllib.request.urlopen(a.url+path,timeout=3) as r:return r.read()
    before=json.loads(read('/api/state'));image=read('/snapshot.png');after=json.loads(read('/api/state'))
    (a.output/f'{i:02d}.png').write_bytes(image)
    (a.output/f'{i:02d}.json').write_text(json.dumps(dict(before=before,after=after,exact_frame_match=False)))
    time.sleep(.1)
