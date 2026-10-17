#!/usr/bin/env python3
"""Read-only preservation of one completed passive Jetson collection.

Remote work only reads four source files and streams tar/xz to stdout. No
hardware APIs, serial ports, services, or remote temporary files are used.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import tarfile

SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o',
       'HostName=100.126.59.18', '-o', 'HostKeyAlias=jetson', 'rbafna@jetson']
REMOTE_CHECK = r'''
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1])
r=json.loads((p/'report.json').read_text())
assert r.get('procedure')=='passive', 'not passive'
assert r.get('completed') is True and r.get('stop_confirmed') is True, 'not complete with STOP'
assert r.get('records_dropped')==0 and not r.get('failure'), 'collection failed or dropped records'
assert not r.get('camera',{}).get('failure'), 'camera collection failed'
raw=r['raw_log'];assert Path(raw).name==raw and raw.startswith('rig-') and raw.endswith('.jsonl')
names=[raw,'vision.ndjson','report.json','vision-report.json'];files={}
for name in names:
 f=p/name;before=f.stat();h=hashlib.sha256()
 with f.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 after=f.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'source changed while hashing'
 files[name]={'bytes':after.st_size,'sha256':h.hexdigest()}
assert files[raw]['sha256']==r['raw_log_sha256'],'raw hash mismatch'
v=json.loads((p/'vision-report.json').read_text())
assert not v.get('failure') and files['vision.ndjson']['sha256']==v['sha256'],'vision hash mismatch'
assert files['vision.ndjson']['sha256']==r['camera']['sha256'],'collection camera hash mismatch'
with (p/raw).open() as stream:session=json.loads(next(stream))['session']
assert str(r['result']['info']['sid'])==session['session_id'],'session mismatch'
print(json.dumps({'remote_directory':str(p),'files':files,'session':session,
 'completed':r['completed'],'stop_confirmed':r['stop_confirmed'],
 'records_dropped':r['records_dropped'],'finish_reason':r['result'].get('finish_reason'),
 'collection_protocol':r.get('collection_protocol'),'raw_sha256':r['raw_log_sha256']}))
'''


def check_remote(directory):
    command = 'python3 - ' + shlex.quote(directory)
    return json.loads(subprocess.check_output(SSH + [command], input=REMOTE_CHECK.encode()))


def sha_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--remote-directory', required=True)
    p.add_argument('--output', required=True, type=Path, help='new evidence subdirectory')
    p.add_argument('--extract-root', required=True, type=Path, help='new ignored runs subdirectory')
    p.add_argument('--xz', default=shutil.which('xz') or 'xz')
    args = p.parse_args()
    if args.output.exists() or args.extract_root.exists():
        raise FileExistsError('output and extraction directory must both be new')
    remote = PurePosixPath(args.remote_directory)
    if not remote.is_absolute() or '..' in remote.parts:
        raise ValueError('absolute remote directory required')
    before = check_remote(str(remote))
    args.output.mkdir(parents=True)
    archive = args.output / 'original.tar.xz'
    members = [str(PurePosixPath(remote.name) / name) for name in before['files']]
    tar_cmd = shlex.join(['tar', '-C', str(remote.parent), '-cf', '-', '--', *members])
    remote_command = shlex.join(['bash', '-o', 'pipefail', '-c', tar_cmd + ' | nice -n 19 xz -T1 -6 -c'])
    with archive.open('xb') as out:
        subprocess.run(SSH + [remote_command], stdout=out, check=True)
    after = check_remote(str(remote))
    if after != before:
        raise RuntimeError('remote source changed across transfer; archive is unverified')
    checked = {}
    args.extract_root.mkdir(parents=True)
    with subprocess.Popen([args.xz, '-dc', str(archive)], stdout=subprocess.PIPE) as proc:
        with tarfile.open(fileobj=proc.stdout, mode='r|') as tar:
            for member in tar:
                if member.name not in members or not member.isfile() or member.name in checked:
                    raise ValueError('unexpected archive member: ' + member.name)
                data = tar.extractfile(member).read()
                actual = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                if actual != before['files'][PurePosixPath(member.name).name]:
                    raise ValueError('archive member hash mismatch: ' + member.name)
                target = args.extract_root / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as out:
                    out.write(data)
                checked[member.name] = actual
        if proc.wait() != 0:
            raise RuntimeError('xz verification failed')
    if set(checked) != set(members):
        raise ValueError('missing archive members')
    manifest = dict(before, fetched_at_utc=datetime.now(timezone.utc).isoformat(),
        source_unchanged_across_transfer=True, archive_sha256=sha_file(archive),
        archive_bytes=archive.stat().st_size, archive_members=checked,
        extraction_root=str(args.extract_root.resolve()),
        remote_tar_command=remote_command, remote_files_modified=False)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'source_sha256':before['raw_sha256'],'session':before['session'],
                     'manifest':str(args.output/'manifest.json')},indent=2))


if __name__ == '__main__':
    main()
