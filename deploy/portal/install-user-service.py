#!/usr/bin/env python3
"""Install an independent loopback portal service. Run from the staged Jetson source."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys


def private_json(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(data,stream,indent=2);stream.write('\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python',type=Path,required=True,help='installed portal virtualenv Python')
    parser.add_argument('--origin',action='append',default=[],help='exact HTTPS Vercel/custom origin; repeatable')
    parser.add_argument('--port',type=int,default=8780)
    args=parser.parse_args()
    if not args.python.is_file():parser.error('Python executable missing')
    if not 1024<=args.port<=65535:parser.error('port must be 1024..65535')
    for origin in args.origin:
        from urllib.parse import urlsplit
        parsed=urlsplit(origin)
        if parsed.scheme!='https' or not parsed.hostname or parsed.netloc!=parsed.hostname or parsed.path or parsed.query or parsed.fragment:
            parser.error('origin must be an exact HTTPS origin without path or credentials')
    home=Path.home();configuration=home/'.config/cartpole-portal';state=home/'.local/state/cartpole-portal'
    units=home/'.config/systemd/user'
    for directory in (configuration,state,units):directory.mkdir(parents=True,exist_ok=True)
    credentials=configuration/'credentials.json';settings=configuration/'service.json'
    if not credentials.exists():
        values={secrets.token_hex(32):[owner,role] for owner,role in [('owner','submit'),('operator','operator'),('jetson-worker','worker')]}
        private_json(credentials,values)
        for token,(_,role) in values.items():
            fd=os.open(configuration/(role+'-token'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as stream:stream.write(token+'\n')
    if credentials.is_symlink():raise ValueError('credentials cannot be a symlink')
    if not settings.exists():
        private_json(settings,{'root':str(state/'store'),'credentials':str(credentials),'origins':args.origin,
            'camera_url':'http://127.0.0.1:3090','rig_id':'cartpole','port':args.port,'reservations_enabled':True})
    elif args.origin:
        raise ValueError('Existing service configuration preserved; update its origins explicitly')
    # Paths are fixed user-owned locations; quote for systemd, not a shell.
    if any(c in str(args.python) for c in '\n\r"%'):raise ValueError('unsupported interpreter path')
    unit=units/'cartpole-portal.service'
    unit.write_text('[Unit]\nDescription=Cartpole authenticated portal API and camera relay\nAfter=network-online.target\n\n'
        '[Service]\nType=simple\n'+f'ExecStart="{args.python.absolute()}" -m cartpole_sdk.portal.host --config "{settings}"\n'
        +f'WorkingDirectory={state}\n'+'Restart=on-failure\nRestartSec=3\nUMask=0077\nNoNewPrivileges=yes\n'
        'RestrictSUIDSGID=yes\nLockPersonality=yes\n\n[Install]\nWantedBy=default.target\n')
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','cartpole-portal.service'],check=True)
    print('Portal API installed on loopback only. No worker, serial connection, or public tunnel started.')
    print('Private configuration:',settings)
    print('Private role-token files:',configuration)


if __name__=='__main__':main()
