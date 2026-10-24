"""Deployment copies move to reviewed runtime while training evidence stays fixed."""
from hashlib import sha256
import json
import random
from pathlib import Path
import pytest
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.policies.neural import NeuralPolicy, load_neural_policy, _digest, RUNTIME_FILES
from cartpole_sdk.policies.rig_observation import rig_channels

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'working.json': ('combined-recovery-20261021-step000102400-rail1mm', '0d17c63c7b779286ab9954da8bc7cc74850f7da235fc393f35867115819dbe16'),
    '1m.json': ('combined-recovery-20261023-step001024000-rail1mm', '0c4207fa9bce067b8822a1f58de0d4853a899a9924923a4d6f247338f001c11a'),
}

@pytest.mark.parametrize('name', SOURCES)
def test_migrated_actor_preserves_training_weights_contracts_and_source(name):
    directory, expected = SOURCES[name]
    source = ROOT/'training/candidates'/directory/'actor.json'
    assert sha256(source.read_bytes()).hexdigest() == expected
    original = json.loads(source.read_text())
    deployed_path = ROOT/'policies'/name
    deployed = json.loads(deployed_path.read_text())
    assert {k:v for k,v in original.items() if k not in ('runtime_sha256','content_sha256')} == {
        k:v for k,v in deployed.items() if k not in ('runtime_sha256','content_sha256')}
    loaded = load_neural_policy(deployed_path, channels=rig_channels(angle_source='filtered'))
    assert loaded.actor == deployed
    migration = json.loads((ROOT/'policies/vertical-runtime-migration.json').read_text())
    record = migration['actors'][name]
    assert record['source_file_sha256'] == expected
    assert record['deployed_file_sha256'] == sha256(deployed_path.read_bytes()).hexdigest()
    assert record['layers_sha256'] == _digest(original['layers'])
    assert record['inference_parity']['max_abs_difference'] == 0
    assert record['inference_parity']['samples'] >= 100
    original_policy = NeuralPolicy(original, channels=rig_channels(angle_source='filtered'))
    rng = random.Random(record['inference_parity']['seed'])
    maximum = 0.
    for _ in range(record['inference_parity']['samples']):
        encoded = {'age_s':[rng.uniform(0,.02) for _ in range(7)],
                   'state':[rng.uniform(-2,2) for _ in range(7)], 'valid':[1.]*7}
        maximum = max(maximum, abs(original_policy.predict_encoded(encoded)-loaded.predict_encoded(encoded)))
    assert maximum == record['inference_parity']['max_abs_difference'] == 0
    assert record['old_runtime_sha256'] == original['runtime_sha256']
    assert record['new_runtime_sha256'] == deployed['runtime_sha256']
    assert set(deployed['runtime_sha256']) == set(RUNTIME_FILES)

@pytest.mark.parametrize('name', SOURCES)
def test_old_pins_still_fail_strict_loader(name, tmp_path):
    deployed = json.loads((ROOT/'policies'/name).read_text())
    deployed['runtime_sha256']['rig/client.py'] = '0'*64
    deployed.pop('content_sha256')
    deployed['content_sha256'] = _digest(deployed)
    path=tmp_path/name;path.write_text(json.dumps(deployed))
    with pytest.raises(ValidationError,match='inference source differs'):
        load_neural_policy(path,channels=rig_channels(angle_source='filtered'))
