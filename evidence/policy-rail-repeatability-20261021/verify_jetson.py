"""Offline release verification on Jetson; no Rig/serial connection is created."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json
from cartpole_sdk.policies.neural import load_neural_policy
from cartpole_sdk.policies.rig_observation import rig_channels
from cartpole_sdk.learning.balance_hardware import BalanceOnlyPolicy
from cartpole_sdk.rig.client import Rig
from cartpole_sdk.rig.parameters import TUNABLE_FIRMWARE
from cartpole_sdk.rig import neural_runner
root=Path.cwd();assert root.name=='id-20261021-policy-rail1mm'
assert Path(neural_runner.__file__).resolve()==root/'src/cartpole_sdk/rig/neural_runner.py'
manifest=json.loads((root/'deployment-files.json').read_text())
for name,digest in manifest.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
results=[]
for path in sorted((root/'training/candidates').glob('*/actor.json')):
 actor=load_neural_policy(path,channels=rig_channels(angle_source='filtered'))
 policy=BalanceOnlyPolicy(actor.actor,channels=rig_channels(angle_source='filtered'),guard_profile='rig',inference_backend='numpy')
 values=dict(policy.executor_parameters,rail=.308962494)
 info=SimpleNamespace(home_epoch=1,measured_span_steps=16504,firmware=TUNABLE_FIRMWARE,rail_half_m=.3089625)
 fake=SimpleNamespace(state=SimpleNamespace(homed=True))
 fake._rail_cap=lambda v,i:Rig._rail_cap(fake,v,i)
 compatibility=neural_runner._live_rail_compatibility(fake,values,policy.executor_parameters,info)
 limits=policy.bind_live_executor(values)
 assert abs(limits['position_m']-.2989625036716461)<1e-9
 results.append(dict(path=str(path.relative_to(root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),compatibility=compatibility,limits=limits))
assert len(results)==3
print(json.dumps(dict(release=str(root),import_path=neural_runner.__file__,actors=results,checks_passed=True,scope='offline reproduction of supplied telemetry values, no live rig access'),indent=2))
