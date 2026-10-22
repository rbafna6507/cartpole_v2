#!/usr/bin/env python3
"""Recover immutable backed checkpoints using the frozen evaluation driver."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BACKUP = ROOT / 'runs/colab-filtered-joint-long-20261021-checkpoints'
DRIVER = ROOT / 'evidence/policy-recovery-20261021/combined-next/run.py'
PROTOCOL = DRIVER.with_name('protocol.json')

def digest(p):
    return sha256(Path(p).read_bytes()).hexdigest()

def save(p, data):
    with p.open('x') as f:
        json.dump(data, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')

def main():
    spec = importlib.util.spec_from_file_location('frozen_combined', DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    driver.torch.set_num_threads(1)
    p = driver.protocol(PROTOCOL)
    last = json.loads((BACKUP / 'last-complete.json').read_text())
    source_report = BACKUP / last['reports'][0]['local_path']
    assert digest(source_report) == last['reports'][0]['sha256']
    report = json.loads(source_report.read_text())
    assert report['arm'] == 'ppo' and report['protocol_sha256'] == digest(PROTOCOL)
    preserved_actor = ROOT / 'training/candidates/balance-recovery-20261021/actor.json'
    preserved_sha = digest(preserved_actor)
    results = []
    save(OUT / 'inputs.json', dict(protocol_sha256=digest(PROTOCOL), driver_sha256=digest(DRIVER),
        backup_last_complete_sha256=digest(BACKUP / 'last-complete.json'),
        source_report_path=str(source_report.relative_to(ROOT)), source_report_sha256=digest(source_report),
        preserved_balance_actor_sha256=preserved_sha, original_run_completed=report['completed'],
        scope='Recover locally backed checkpoint artifacts without completing or altering original run reports.'))
    for step in (102400, 460800):
        receipt = next(c for c in last['checkpoints'] if c['step'] == step)
        cp = BACKUP / receipt['local_path']
        cp_report = next(c for c in report['checkpoints'] if c['step'] == step)
        assert digest(cp) == receipt['sha256'] == cp_report['sha256']
        with zipfile.ZipFile(cp) as z:
            assert z.testzip() is None
        model = driver.EquilibriumPPO.load(cp, device='cpu')
        assert model.num_timesteps == step
        assert driver.model_weights_sha256(model) == cp_report['weights_sha256']
        assert driver.actor_weights_hash(model) == cp_report['actor_weights_sha256']
        print(f'validated checkpoint {step}', flush=True)
        destination = ROOT / f'training/candidates/combined-recovery-20261021-step{step:09d}'
        destination.mkdir(parents=True, exist_ok=False)
        evaluations = []
        for numeric in (False, True):
            eval_out = OUT / f'step-{step:09d}-nominal-{ "numpy" if numeric else "sb3" }'
            evaluation = driver.evaluate(model, p, eval_out, seconds=25., numeric=numeric,
                checkpoint_sha256=digest(cp), protocol_sha256=digest(PROTOCOL))
            evaluations.append(dict(path=str(eval_out.relative_to(ROOT)), numeric=numeric,
                                    report_sha256=digest(eval_out / 'report.json'), summary=evaluation['summary']))
            print(json.dumps(dict(step=step, numeric=numeric, summary=evaluation['summary'])), flush=True)
        parity_out = OUT / f'step-{step:09d}-sdk-parity'
        parity = driver.check_candidate(model, p['experiment'], parity_out,
            checkpoint_sha256=digest(cp), seeds=p['development_seeds'][:2], seconds=5.)
        assert parity['emission_parity_pass'] and not parity['rejected_inputs']
        shutil.copyfile(parity_out / 'actor.json', destination / 'actor.json')
        from cartpole_sdk.rig.console_policy import ConsolePolicy
        policy = ConsolePolicy.validate_actor(destination / 'actor.json')
        from cartpole_sdk.learning.balance_hardware import _load_policy
        runtime = _load_policy(destination / 'actor.json', guard_profile='rig', inference_backend='numpy')
        item = dict(status='DEVELOPMENT_ONLY', hardware_accepted=False, step=step,
            checkpoint_path=str(cp.relative_to(ROOT)), checkpoint_sha256=digest(cp),
            model_weights_sha256=driver.model_weights_sha256(model), actor_weights_sha256=driver.actor_weights_hash(model),
            actor_file_sha256=digest(destination / 'actor.json'), actor_content_sha256=policy.actor['content_sha256'],
            actor_runtime_sha256=policy.actor['runtime_sha256'], candidate_path=str(destination.relative_to(ROOT)),
            protocol_sha256=digest(PROTOCOL), driver_sha256=digest(DRIVER),
            nominal_development_evaluations=evaluations, sdk_parity_path=str(parity_out.relative_to(ROOT)),
            sdk_parity_report_sha256=digest(parity_out / 'report.json'),
            sdk_parity_pass=parity['emission_parity_pass'], sdk_parity_compared_actions=parity['compared_actions'],
            sdk_parity_max_abs_error_m_s2=parity['max_abs_raw_discrepancy_m_s2'],
            local_console_load_pass=True, local_numpy_runtime_load_pass=True,
            console_start='upright only; centered, nearly stationary; no supported hanging start option',
            console_run_limits=policy.run_limits, action_scale_m_s2=policy.actor['action_scale_m_s2'],
            observation_contract=policy.observation_contract,
            limitations=['Nominal development poses only; no stress or held-out confirmation in this recovery.',
                'No hardware execution or acceptance. Hanging simulations use native rail braking near rail ends.',
                'The existing console requires upright admission regardless of combined training.'])
        save(destination / 'recovery-manifest.json', item)
        results.append(item)
        print(json.dumps(dict(step=step, parity_pass=True, candidate=str(destination), actor_sha256=item['actor_file_sha256'])), flush=True)
    assert digest(preserved_actor) == preserved_sha
    driver.protocol(PROTOCOL)
    save(OUT / 'candidates.json', dict(candidates=results, preserved_balance_actor_unchanged=True))

if __name__ == '__main__':
    main()
