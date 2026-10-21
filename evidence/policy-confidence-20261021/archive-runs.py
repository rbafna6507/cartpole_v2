#!/usr/bin/env python3
"""Archive every retained run, verify every payload, and split for Git storage."""
from hashlib import sha256
import json
from pathlib import Path
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'runs/policy-confidence-20261021'

def file_hash(path):
    h=sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def main():
    manifest=HERE/'archive-manifest.json'
    if manifest.exists() or list(HERE.glob('runs.tar.gz.part-*')):raise FileExistsError('archive already exists')
    files=sorted(p for p in SOURCE.rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts)
    entries={str(p.relative_to(ROOT)):dict(sha256=file_hash(p),bytes=p.stat().st_size) for p in files}
    with tempfile.TemporaryDirectory(prefix='cartpole-confidence-archive-') as temporary:
        archive=Path(temporary)/'runs.tar.gz'
        with tarfile.open(archive,'w:gz',compresslevel=6) as tar:
            for path in files:tar.add(path,arcname=str(path.relative_to(ROOT)),recursive=False)
        seen=set()
        with tarfile.open(archive,'r:gz') as tar:
            for member in tar:
                if not member.isfile() or member.name not in entries:raise ValueError('unexpected archive member')
                h=sha256();size=0
                with tar.extractfile(member) as stream:
                    for data in iter(lambda:stream.read(1024*1024),b''):h.update(data);size+=len(data)
                if dict(sha256=h.hexdigest(),bytes=size)!=entries[member.name]:raise ValueError('archive verification failed: '+member.name)
                seen.add(member.name)
        if seen!=set(entries):raise ValueError('archive member set mismatch')
        # Detect files changing while the archive was created or verified.
        if any(file_hash(ROOT/name)!=entry['sha256'] for name,entry in entries.items()):raise ValueError('run changed during archive')
        parts=[]
        with archive.open('rb') as stream:
            for index,data in enumerate(iter(lambda:stream.read(48*1024*1024),b'')):
                path=HERE/f'runs.tar.gz.part-{index:03d}'
                with path.open('xb') as target:target.write(data)
                parts.append(dict(path=path.name,bytes=len(data),sha256=sha256(data).hexdigest()))
        result=dict(schema='cartpole-verified-run-archive-v1',archive_sha256=file_hash(archive),archive_bytes=archive.stat().st_size,
            payload_files=len(entries),uncompressed_bytes=sum(e['bytes'] for e in entries.values()),parts=parts,files=entries,
            verification='Every decompressed payload read back and hashed; original files rechecked after archive verification.')
        with manifest.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
        print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))
if __name__=='__main__':main()
