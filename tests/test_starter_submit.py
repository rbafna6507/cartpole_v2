"""Starter CLI exercises real authenticated local HTTP; no worker or rig is started."""
import json
import os
from pathlib import Path
import subprocess
import sys
from test_portal_client import portal


def test_starter_uploads_same_artifact_with_idempotency(portal):
    store,client=portal
    root=Path(__file__).resolve().parents[1]
    command=[sys.executable,str(root/'examples/controller_starter/submit.py'),'--key','starter-test','--seconds','.1']
    environment=dict(os.environ,CARTPOLE_PORTAL_URL=client.origin,CARTPOLE_SUBMIT_TOKEN='alice-secret-long')
    first=subprocess.run(command,cwd=root,env=environment,capture_output=True,text=True,check=True,timeout=10)
    second=subprocess.run(command,cwd=root,env=environment,capture_output=True,text=True,check=True,timeout=10)
    one,two=json.loads(first.stdout),json.loads(second.stdout)
    assert one==two and one['status']=='pending'
    assert store.artifact(one['artifact'])==(root/'examples/controller_starter/policy.py').read_bytes()
    assert len(client.jobs())==1
