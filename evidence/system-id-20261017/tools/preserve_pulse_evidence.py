#!/usr/bin/env python3
"""Copy completed raw experimental files into a compressed, hashed evidence tree.

Usage: preserve_pulse_evidence.py SOURCE_DIRECTORY NEW_EVIDENCE_DIRECTORY
Does not edit the source; JSONL/NDJSON contents are preserved byte-for-byte in gzip.
"""
import argparse,gzip,hashlib,json,shutil
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
manifest={}
for src in sorted(a.source.rglob('*')):
    if not src.is_file():continue
    relative=src.relative_to(a.source);raw=src.read_bytes();target=a.output/relative
    if src.suffix in ('.jsonl','.ndjson'):
        target=target.with_name(target.name+'.gz');payload=gzip.compress(raw,mtime=0)
    else:payload=raw
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    manifest[str(relative)]=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),stored_as=str(target.relative_to(a.output)),stored_sha256=hashlib.sha256(payload).hexdigest())
(a.output/'preservation.json').write_text(json.dumps(dict(schema='cartpole-raw-preservation-v1',sources=manifest),indent=2)+'\n')
print('Preserved',len(manifest),'files')
