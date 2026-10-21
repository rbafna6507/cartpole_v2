import json
from pathlib import Path
from hashlib import sha256
from stable_baselines3 import PPO
from cartpole_sdk.learning.ppo import export_actor
from cartpole_sdk.policies.neural import validate_actor, load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels
root=Path('/Users/rbafna/projects/cartpole_v2')
source=root/'training/candidates/balance-20261020/actor.json'
old=validate_actor(json.loads(source.read_text()))
run=root/'runs/local-balance-20261020/teacher-seed17'
recipe=json.loads((run/'recipe.json').read_text())
checkpoint=run/'checkpoints/step-000020480.zip'
assert sha256(checkpoint.read_bytes()).hexdigest()==old['checkpoint_sha256']
model=PPO.load(checkpoint,device='cpu')
manifest=dict(experiment=recipe['experiment'],experiment_sha256=old['experiment_sha256'],checkpoint_sha256=old['checkpoint_sha256'],action_scale_m_s2=old['action_scale_m_s2'])
actor=export_actor(model,manifest)
assert all(actor[k]==old[k] for k in old if k not in ('content_sha256','runtime_sha256'))
changed=[k for k in old['runtime_sha256'] if old['runtime_sha256'][k]!=actor['runtime_sha256'][k]]
assert changed==['rig/neural_runner.py'],changed
out=root/'training/candidates/balance-20261021-console';out.mkdir(exist_ok=True)
p=out/'actor.json';p.write_text(json.dumps(actor,indent=2,sort_keys=True)+'\n')
load_neural_policy(p,channels=rig_channels(angle_source='raw'))
report=dict(status='DEVELOPMENT_ONLY',hardware_accepted=False,parent_file_sha256=sha256(source.read_bytes()).hexdigest(),parent_content_sha256=old['content_sha256'],checkpoint=str(checkpoint.relative_to(root)),checkpoint_sha256=old['checkpoint_sha256'],actor_file_sha256=sha256(p.read_bytes()).hexdigest(),actor_content_sha256=actor['content_sha256'],changed_runtime_files=changed,weights_and_all_other_actor_fields_identical=True,reason='Re-export exact trusted local PPO checkpoint against reviewed two-counted-step HOME compatibility. No retraining or acceptance change.')
(out/'export.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(report))
