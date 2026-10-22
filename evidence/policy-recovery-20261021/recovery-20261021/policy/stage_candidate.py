#!/usr/bin/env python3
"""Additively stage a verified numeric actor; never connect to a rig."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
REMOTE = '/home/rbafna/cartpole-v2-live/releases/id-20261021-policy-console'
REMOTE_CODE = r'''
import base64
from hashlib import sha256
import json
from pathlib import Path
import sys
payload = json.load(sys.stdin)
root = Path.cwd()
assert str(root) == payload['release']
for name, expected in payload['source_sha256'].items():
    assert sha256((root / name).read_bytes()).hexdigest() == expected, name
baseline = root / 'training/candidates/balance-recovery-20261021/actor.json'
assert sha256(baseline.read_bytes()).hexdigest() == payload['balance_actor_sha256']
target = root / payload['candidate_path']
assert target.parent == root / 'training/candidates' and target.name.startswith('combined-recovery-20261021-step')
assert set(payload['files']) == {'actor.json', 'recovery-manifest.json'}
blobs = {}
for name, file in payload['files'].items():
    raw = base64.b64decode(file['data'], validate=True)
    assert sha256(raw).hexdigest() == file['sha256']
    blobs[name] = raw
target.mkdir(exist_ok=False)
for name, raw in blobs.items():
    with (target / name).open('xb') as stream:
        stream.write(raw)
from cartpole_sdk.rig.console_policy import ConsolePolicy
from cartpole_sdk.learning.balance_hardware import _load_policy
policy = ConsolePolicy.validate_actor(target / 'actor.json')
runtime = _load_policy(target / 'actor.json', guard_profile='rig', inference_backend='numpy')
assert sha256(baseline.read_bytes()).hexdigest() == payload['balance_actor_sha256']
print(json.dumps(dict(release=str(root), candidate_path=str(target),
    actor_file_sha256=sha256((target / 'actor.json').read_bytes()).hexdigest(),
    actor_content_sha256=policy.actor['content_sha256'], runtime_load_pass=True,
    numpy_runtime_load_pass=True, source_files_matched=len(payload['source_sha256']),
    numpy_backend=runtime.inference_provenance, preserved_balance_actor_unchanged=True,
    no_serial_access=True, no_hardware_commands=True, no_existing_files_changed=True,
    console_admission='Existing upright-start admission remains required.', hardware_accepted=False),
    indent=2, sort_keys=True))
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', type=int, choices=(102400,460800), required=True)
    args=parser.parse_args()
    candidate=ROOT / f'training/candidates/combined-recovery-20261021-step{args.step:09d}'
    manifest=json.loads((candidate/'recovery-manifest.json').read_text())
    assert manifest['sdk_parity_pass'] and manifest['local_console_load_pass']
    assert sha256((candidate/'actor.json').read_bytes()).hexdigest()==manifest['actor_file_sha256']
    before=json.loads((OUT/'jetson-runtime-before.json').read_text())
    for name, expected in before['source_sha256'].items():
        assert sha256((ROOT/name).read_bytes()).hexdigest()==expected, name
    payload=dict(release=REMOTE, source_sha256=before['source_sha256'],
        balance_actor_sha256=before['balance_actor_sha256'],candidate_path=str(candidate.relative_to(ROOT)),
        files={name:dict(sha256=sha256((candidate/name).read_bytes()).hexdigest(),
              data=base64.b64encode((candidate/name).read_bytes()).decode())
              for name in ('actor.json','recovery-manifest.json')})
    command=f'cd {shlex.quote(REMOTE)} && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c {shlex.quote(REMOTE_CODE)}'
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','rbafna@jetson',command],
        input=json.dumps(payload),text=True,capture_output=True,timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr)
    report=json.loads(result.stdout)
    assert report['actor_file_sha256']==manifest['actor_file_sha256'] and report['runtime_load_pass']
    with (OUT/f'jetson-staged-{args.step:09d}.json').open('x') as stream:
        json.dump(report,stream,indent=2,sort_keys=True)
        stream.write('\n')
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=='__main__':
    main()
