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
    p.add_argument('command',choices=('start','status','download','stop'))
    p.add_argument('bundle',type=Path)
    p.add_argument('--session',required=True,help='Unique named Colab session for this experiment.')
    p.add_argument('--colab',type=Path,default=Path('runs/colab-cli-venv/bin/colab'))
    p.add_argument('--output',type=Path,help='New local results ZIP; required for download.')
    p.add_argument('--state-file',type=Path,default=Path.home()/'.config/colab-cli/sessions.json',
                   help='Pinned CLI session registry; existing names cannot be reallocated.')
    a=p.parse_args(argv)
    from cartpole_sdk.learning.colab_bundle import verify_bundle
    try:
        verify_bundle(a.bundle)
        executable=a.colab.resolve()
        if not executable.is_file():
            raise ValueError('Install google-colab-cli==0.7.4 first; see docs/rl-training.md.')
        if a.command=='download' and (a.output is None or a.output.exists()):
            raise ValueError('download requires a new --output ZIP path')
        base=[str(executable),'--auth','oauth2','--config',str(a.state_file)]
        def call(*args):
            subprocess.run(base+list(args),check=True)
        def remote(action,timeout=60):
            # CLI0.7.4 can exit0 despite a remote Python exception. Require a
            # fresh success receipt from this exact invocation, never exit0 alone.
            nonce=uuid.uuid4().hex
            result=subprocess.run(base+['exec','-s',a.session,'--timeout',str(timeout),
                '-f',str(a.bundle/'remote.py'),'--env','CARTPOLE_ACTION='+action,
                '--env','CARTPOLE_NONCE='+nonce],check=True,text=True,capture_output=True)
            print(result.stdout,end='')
            print(result.stderr,end='',file=sys.stderr)
            expected={'action':action,'nonce':nonce}
            prefix='CARTPOLE_REMOTE_OK '
            receipts=[]
            for line in result.stdout.splitlines():
                if line.startswith(prefix):
                    try:receipts.append(json.loads(line[len(prefix):]))
                    except ValueError:pass
            if receipts != [expected]:
                raise ValueError('remote '+action+' has no matching success receipt; inspect session before retrying')
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
        elif a.command=='download':
            remote('package',300)
            a.output.parent.mkdir(parents=True,exist_ok=True)
            call('download','-s',a.session,'/content/cartpole-results.zip',str(a.output))
            import zipfile
            with zipfile.ZipFile(a.output) as z:
                if z.testzip() is not None:raise ValueError('downloaded ZIP failed CRC check')
            print('Downloaded and CRC-checked '+str(a.output))
        else:call('stop','-s',a.session)
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        p.exit(2,str(error)+'\nNo cloud action is retried automatically. Inspect status before retrying a launch.\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
