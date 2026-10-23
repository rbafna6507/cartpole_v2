#!/usr/bin/env python3
"""Install an outbound-pull worker; hardware starts only with explicit --start."""
import argparse
import math
from pathlib import Path
import subprocess


def quoted(value):
    value=str(value)
    if any(c in value for c in '\n\r\x00%$"\\'):raise ValueError('unsupported unit argument')
    return '"'+value+'"'


def unit_text(python, home, backend, port=None, *, max_acceleration=.25, numpy_root=None, sandbox_cpu=None):
    home=Path(home)
    if type(max_acceleration) not in (int,float) or not math.isfinite(max_acceleration) or not 0<max_acceleration<=25:raise ValueError("acceleration ceiling must be within (0,25]")
    if backend not in ('simulation','hardware'):raise ValueError('invalid backend')
    if backend=='hardware' and (not port or not str(port).startswith('/dev/')):raise ValueError('explicit device required')
    state=home/'.local/state/cartpole-portal'
    args=[python,'-c','from cartpole_sdk.portal.worker import main; raise SystemExit(main())','--portal','http://127.0.0.1:8780',
          '--token-file',home/'.config/cartpole-portal/worker-token','--worker','jetson-worker',
          '--rig-id','cartpole' if backend=='hardware' else 'cartpole-simulation',
          '--backend',backend,'--recording-root',state/(backend+'-recordings'),
          '--spool-root',state/(backend+'-spool')]
    if sandbox_cpu is not None:
        if type(sandbox_cpu) is not int or sandbox_cpu<0:raise ValueError('invalid sandbox CPU')
        args+=['--sandbox-cpu',str(sandbox_cpu)]
    if numpy_root is not None:args+=['--numpy-root',str(numpy_root)]
    if backend=='hardware':args+=['--port',port,'--rate','100','--max-acceleration',str(float(max_acceleration)),
                                '--log-dir',state/'hardware-logs']
    return ('[Unit]\nDescription=Cartpole '+backend+' isolated submission worker\nAfter=cartpole-portal.service\n\n'
            '[Service]\nType=simple\nExecStart='+' '.join(map(quoted,args))+'\n'
            'WorkingDirectory='+str(state)+'\nUMask=0077\nNoNewPrivileges=yes\n'
            'RestrictSUIDSGID=yes\nLockPersonality=yes\nKillMode=control-group\nTimeoutStopSec=5\n'
            'Restart=no\n\n[Install]\nWantedBy=default.target\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python',type=Path,required=True)
    parser.add_argument('--backend',choices=('simulation','hardware'),required=True)
    parser.add_argument('--sandbox-cpu',type=int,help='trusted CPU assigned to the isolated child')
    parser.add_argument('--numpy-root',type=Path,help='trusted read-only NumPy runtime matching sandbox system Python')
    parser.add_argument('--max-acceleration',type=float,default=.25,help='trusted hardware demand ceiling in (0,25] m/s²')
    parser.add_argument('--port',help='explicit hardware serial device')
    parser.add_argument('--start',action='store_true',help='start now after installation; does not enable boot startup')
    parser.add_argument('--enable',action='store_true',help='explicitly enable startup on future user sessions/boots')
    args=parser.parse_args()
    if not args.python.is_file():parser.error('Python executable missing')
    home=Path.home();state=home/'.local/state/cartpole-portal'
    if not (home/'.config/cartpole-portal/worker-token').is_file():parser.error('install API service credentials first')
    content=unit_text(args.python.absolute(),home,args.backend,args.port,max_acceleration=args.max_acceleration,numpy_root=args.numpy_root,sandbox_cpu=args.sandbox_cpu)
    for suffix in ('spool','recordings'):(state/(args.backend+'-'+suffix)).mkdir(parents=True,exist_ok=True,mode=0o700)
    units=home/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
    name='cartpole-worker-'+args.backend+'.service';(units/name).write_text(content)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    if args.enable:subprocess.run(['systemctl','--user','enable',name],check=True)
    if args.start:subprocess.run(['systemctl','--user','start',name],check=True)
    print(name+' installed'+(', boot startup enabled' if args.enable else '')+(', started' if args.start else ', not started'))


if __name__=='__main__':main()
