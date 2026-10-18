#!/usr/bin/env python3
"""Archive complete local run directories with SHA-256 verification. Uses system Python/lzma."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import tarfile


def split_verified_archive(path, manifest, part_bytes=48*1024*1024):
    """Keep Git objects below host size limits; verify concatenation before deletion."""
    if path.stat().st_size<=part_bytes:return manifest
    parts=[];combined=sha256()
    with path.open('rb') as source:
        index=0
        while chunk:=source.read(part_bytes):
            part=path.with_name(path.name+f'.part-{index:03d}')
            with part.open('xb') as stream:stream.write(chunk)
            recovered=part.read_bytes();combined.update(recovered)
            parts.append(dict(path=part.name,bytes=len(recovered),sha256=sha256(recovered).hexdigest()));index+=1
    if combined.hexdigest()!=manifest['archive_sha256']:raise ValueError('split archive concatenation mismatch')
    manifest['parts']=parts
    manifest['restore']='Concatenate parts in listed order to reconstruct archive, then verify archive_sha256 before extraction.'
    path.with_suffix(path.suffix+'.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    path.unlink()
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('roots',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.with_suffix(a.output.suffix+'.manifest.json').exists():raise FileExistsError(a.output)
    files=[]
    for root in a.roots:
        if root.is_absolute() or '..' in root.parts:raise ValueError('roots must be repository-relative')
        for path in sorted(root.rglob('*')):
            if path.is_symlink():raise ValueError('symlinks not allowed')
            if path.is_file():files.append(path)
    if len(set(files))!=len(files):raise ValueError('overlapping roots')
    rows=[dict(path=str(f),size=f.stat().st_size,sha256=sha256(f.read_bytes()).hexdigest()) for f in files]
    with tarfile.open(a.output,'x:xz',preset=3) as archive:
        for path in files:archive.add(path,arcname=str(path),recursive=False)
    with tarfile.open(a.output,'r:xz') as archive:
        members=archive.getmembers()
        if len(members)!=len(rows):raise ValueError('archive membership mismatch')
        for row,member in zip(rows,members):
            stream=archive.extractfile(member)
            if member.name!=row['path'] or stream is None or sha256(stream.read()).hexdigest()!=row['sha256']:raise ValueError('archive hash mismatch')
            if sha256(Path(row['path']).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('source changed while archiving')
    size=a.output.stat().st_size
    manifest=dict(archive=a.output.name,archive_sha256=sha256(a.output.read_bytes()).hexdigest(),files=rows,verified=True)
    a.output.with_suffix(a.output.suffix+'.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    manifest=split_verified_archive(a.output,manifest)
    print(json.dumps(dict(archive=str(a.output),files=len(rows),bytes=size,parts=len(manifest.get('parts',[])),verified=True)))

if __name__=='__main__':main()
