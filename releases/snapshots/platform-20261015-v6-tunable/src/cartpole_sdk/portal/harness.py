"""Bwrap child entrypoint. Only this restricted child imports submitted code."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import math
import os
import sys

# -I -S: explicit readonly SDK path; no user site/customization is imported.
sys.path.insert(0,'/sdk')
sys.dont_write_bytecode=True
if os.path.isdir('/packages/numpy'):
    sys.path.append('/packages')
from cartpole_sdk.contracts import Acceleration
from cartpole_sdk.recording import _session, _observation, canonical_json, strict_json_loads
from cartpole_sdk.portal.security import install_limits

def read_message():
    line=sys.stdin.buffer.readline(65537)
    if len(line)>65536 or not line.endswith(b'\n'):raise ValueError('invalid input framing')
    value=strict_json_loads(line.decode())
    if not isinstance(value,dict):raise ValueError('message must be object')
    return value

def emit(value):
    sys.stdout.write(canonical_json(value)+'\n');sys.stdout.flush()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wall',type=float,required=True)
    parser.add_argument('--memory',type=int,required=True)
    args=parser.parse_args()
    # Entire restriction setup must succeed before uploaded Python is loaded.
    install_limits(args.wall,args.memory)
    reset=read_message()
    if set(reset)!= {'type','session','nonce'} or reset['type']!='reset':raise ValueError('reset first')
    session=_session(reset['session'])
    spec=importlib.util.spec_from_file_location('submitted_policy','/policy/source.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policy=module.create_policy()
    policy.reset(session)
    emit({'type':'reset_ack','nonce':reset['nonce']})
    previous=0
    while True:
        message=read_message()
        if set(message)!= {'type','sequence','observation'} or message['type']!='act' or type(message['sequence']) is not int or message['sequence']<=previous:raise ValueError('invalid action message')
        observation=_observation(message['observation'])
        intent=policy.act(observation)
        if intent is not None and not isinstance(intent,Acceleration):raise ValueError('policy must return Acceleration or None')
        value=None if intent is None else intent.acceleration_m_s2
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):raise ValueError('nonfinite policy output')
        previous=message['sequence']
        emit({'type':'action','sequence':previous,'acceleration':value})

if __name__=='__main__':
    try:main()
    except Exception:
        # Do not expose uploaded stack traces/paths to the trusted API.
        sys.stderr.write('isolated policy failed\n');sys.stderr.flush()
        raise SystemExit(1)
