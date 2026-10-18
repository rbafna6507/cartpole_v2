#!/usr/bin/env python3
"""Operate an explicit Colab CLI session. start allocates a real CPU VM and launches training."""
import argparse
import json
from hashlib import sha256
import sys
import uuid
from pathlib import Path
import subprocess


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('start','status','download','watch','stop'))
    p.add_argument('bundle',type=Path)
    p.add_argument('--session',required=True,help='Unique named Colab session for this experiment.')
    p.add_argument('--colab',type=Path,default=Path('runs/colab-cli-venv/bin/colab'))
    p.add_argument('--output',type=Path,help='New local results ZIP; required for download.')
    p.add_argument('--state-file',type=Path,default=Path.home()/'.config/colab-cli/sessions.json',
                   help='Pinned CLI session registry; existing names cannot be reallocated.')
    p.add_argument('--poll-seconds',type=float,default=60.)
    p.add_argument('--max-seconds',type=float,default=28800.)
    a=p.parse_args(argv)
    from cartpole_sdk.learning.colab_bundle import verify_bundle
    try:
        verify_bundle(a.bundle)
        executable=a.colab.resolve()
        if not executable.is_file():
            raise ValueError('Install google-colab-cli==0.7.4 first; see docs/rl-training.md.')
        if a.command in {'download','watch'} and (a.output is None or a.output.exists()):
            raise ValueError('download/watch requires a new --output path')
        base=[str(executable),'--auth','oauth2','--config',str(a.state_file)]
        def call(*args):
            # Bound transport operations too; the upstream downloader has no HTTP timeout.
            subprocess.run(base+list(args),check=True,timeout=600)
        def remote(action,timeout=60):
            # CLI0.7.4 can exit0 despite a remote Python exception. Require a
            # fresh success receipt from this exact invocation, never exit0 alone.
            nonce=uuid.uuid4().hex
            try:
                result=subprocess.run(base+['exec','-s',a.session,'--timeout',str(timeout),
                    '-f',str(a.bundle/'remote.py'),'--env','CARTPOLE_ACTION='+action,
                    '--env','CARTPOLE_NONCE='+nonce],check=True,text=True,capture_output=True,timeout=timeout+90)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
                def decoded(value):
                    return value.decode(errors='replace') if isinstance(value,bytes) else (value or '')
                print(decoded(error.stdout),end='')
                print(decoded(error.stderr),end='',file=sys.stderr)
                raise
            print(result.stdout,end='',flush=True)
            print(result.stderr,end='',file=sys.stderr,flush=True)
            expected={'action':action,'nonce':nonce}
            prefix='CARTPOLE_REMOTE_OK '
            receipts=[]
            for line in result.stdout.splitlines():
                if line.startswith(prefix):
                    try:receipts.append(json.loads(line[len(prefix):]))
                    except ValueError:pass
            if receipts != [expected]:
                raise ValueError('remote '+action+' has no matching success receipt; inspect session before retrying')
            return result.stdout
        def record(text,prefix):
            rows=[json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]
            if len(rows)!=1:
                raise ValueError('missing structured '+prefix.strip()+'; prepare a new bundle for watch')
            return rows[0]
        def download(destination):
            import zipfile
            reply=remote('package',300)
            if 'CARTPOLE_PACKAGE ' in reply:
                metadata=record(reply,'CARTPOLE_PACKAGE ')
            else:
                # Older immutable bundles print the same package metadata without a prefix.
                rows=[]
                for line in reply.splitlines():
                    try:item=json.loads(line)
                    except ValueError:continue
                    if isinstance(item,dict) and item.get('path')=='/content/cartpole-results.zip':rows.append(item)
                if len(rows)!=1:raise ValueError('missing package hash receipt')
                metadata=rows[0]
            destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_suffix(destination.suffix+'.part')
            if destination.exists() or temporary.exists():raise FileExistsError(destination)
            call('download','-s',a.session,'/content/cartpole-results.zip',str(temporary))
            actual=sha256(temporary.read_bytes()).hexdigest()
            if actual!=metadata['sha256'] or temporary.stat().st_size!=metadata['bytes']:
                raise ValueError('downloaded archive hash/size mismatch; partial file retained')
            with zipfile.ZipFile(temporary) as archive:
                if archive.testzip() is not None:raise ValueError('downloaded ZIP failed CRC check')
            temporary.rename(destination)
            print('Downloaded and SHA256/CRC-checked '+str(destination),flush=True)
            return dict(sha256=actual,bytes=metadata['bytes'])
        if a.command=='start':
            # CLI new overwrites duplicate names. Check its exact registry and
            # reserve locally before allocating; preserve reservation on failure.
            if a.state_file.exists():
                registry=json.loads(a.state_file.read_text())
                if not isinstance(registry,dict):raise ValueError('invalid CLI session registry')
                if a.session in registry:
                    raise ValueError('session name already exists; use status, not start')
            a.state_file.parent.mkdir(parents=True,exist_ok=True)
            reservation=a.state_file.parent/('.cartpole-launch-'+sha256(a.session.encode()).hexdigest()+'.json')
            with reservation.open('x') as stream:
                json.dump(dict(session=a.session,bundle=str(a.bundle.resolve())),stream)
            call('new','-s',a.session)
            for local,destination in (('source.zip','source.zip'),('inputs.zip','inputs.zip'),('remote.py','cartpole-launch.py')):
                call('upload','-s',a.session,str(a.bundle/local),'/content/'+destination)
            remote('setup',1800)
            remote('start',60)
        elif a.command=='status':remote('status')
        elif a.command=='download':download(a.output)
        elif a.command=='watch':
            from cartpole_sdk.learning.colab_watch import watch_job
            result=watch_job(lambda:record(remote('status'),'CARTPOLE_STATUS '),download,a.output,
                             poll_seconds=a.poll_seconds,max_seconds=a.max_seconds)
            print(json.dumps(result,indent=2))
            if result['status']!='completed':return 2
        else:call('stop','-s',a.session)
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        p.exit(2,str(error)+'\nNo cloud action is retried automatically. Inspect status before retrying a launch.\n')
    except KeyboardInterrupt:
        p.exit(130,'Local operation interrupted; the remote job was not stopped.\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
