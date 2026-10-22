#!/usr/bin/env python3
"""Create explicitly versioned actor bindings for the 1 mm HOME admission change."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import numpy as np
from cartpole_sdk.policies.neural import RUNTIME_FILES, _digest, load_neural_policy, validate_actor
from cartpole_sdk.policies.numeric_backend import NumpyActorBackend
from cartpole_sdk.policies.rig_observation import rig_channels
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SOURCES=('balance-recovery-20261021','combined-recovery-20261021-step000102400','combined-recovery-20261021-step000460800')

def main():
    package=ROOT/'src/cartpole_sdk'
    actual={name:sha256((package/name).read_bytes()).hexdigest() for name in RUNTIME_FILES}
    prior_source=subprocess.run(['git','show','6145319:src/cartpole_sdk/rig/neural_runner.py'],cwd=ROOT,check=True,capture_output=True).stdout
    prior_hash=sha256(prior_source).hexdigest();results=[]
    for name in SOURCES:
        source=ROOT/'training/candidates'/name/'actor.json'
        before=validate_actor(json.loads(source.read_text()))
        assert before['runtime_sha256']['rig/neural_runner.py']==prior_hash
        changed=[key for key in RUNTIME_FILES if before['runtime_sha256'][key]!=actual[key]]
        assert changed==['rig/neural_runner.py'],changed
        actor=deepcopy(before);actor['runtime_sha256']=actual
        actor.pop('content_sha256');actor['content_sha256']=_digest(actor)
        output=ROOT/'training/candidates'/(name+'-rail1mm');output.mkdir(exist_ok=False)
        path=output/'actor.json';path.write_text(json.dumps(actor,indent=2,sort_keys=True)+'\n')
        loaded=load_neural_policy(path,channels=rig_channels(angle_source=actor['angle_source']))
        for key in set(before)-{'runtime_sha256','content_sha256'}:assert loaded.actor[key]==before[key],key
        old_backend=NumpyActorBackend(before);new_backend=NumpyActorBackend(loaded.actor)
        rng=np.random.default_rng(29219);error=0.
        for _ in range(4096):
            observation=dict(state=rng.uniform(-5,5,7),age_s=rng.uniform(0,.02,7),valid=rng.integers(0,2,7))
            error=max(error,abs(old_backend.predict_encoded(observation)-new_backend.predict_encoded(observation)))
        assert error==0
        receipt=dict(source_actor=str(source.relative_to(ROOT)),source_file_sha256=sha256(source.read_bytes()).hexdigest(),source_content_sha256=before['content_sha256'],
            actor_path=str(path.relative_to(ROOT)),actor_file_sha256=sha256(path.read_bytes()).hexdigest(),actor_content_sha256=actor['content_sha256'],
            checkpoint_sha256=actor['checkpoint_sha256'],unchanged_actor_fields=sorted(set(before)-{'runtime_sha256','content_sha256'}),
            runtime_changes={key:dict(before=before['runtime_sha256'][key],after=actual[key]) for key in changed},
            reason='Admit up to 1 mm HOME half-length variation while retaining strict current cap and trained/live envelope intersection.',
            hardware_accepted=False,predictions_compared=4096,max_abs_prediction_difference_m_s2=error)
        (output/'runtime-rebind.json').write_text(json.dumps(receipt,indent=2)+'\n');results.append(receipt)
    (HERE/'actors.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps([dict(actor=r['actor_path'],max_error=r['max_abs_prediction_difference_m_s2']) for r in results]))
if __name__=='__main__':main()
