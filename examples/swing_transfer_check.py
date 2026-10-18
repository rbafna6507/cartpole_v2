#!/usr/bin/env python3
"""Run current offline transfer checks over a trusted, verified frozen swing run.

The original archived loader retains every training source/dependency guard.
The current evaluator is a separately hashed tool using that frozen runtime.
No network, environment installation, hardware commands, or deployment approval.
"""
import argparse
from hashlib import sha256
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GUARDS_PATH = Path(__file__).with_name('replay_balance_evaluation.py')
EVALUATOR_PATH = ROOT/'src/cartpole_sdk/learning/transfer_checks.py'
PARITY_PATH = ROOT/'src/cartpole_sdk/learning/candidate_parity.py'
SCHEMA = 'cartpole-swing-learning-v1'


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guards = _module('swing_transfer_replay_guards', GUARDS_PATH)


def _check_pins(pins):
    if any(sha256(guards._read_file(Path(path))).hexdigest() != pin for path,pin in pins.items()):
        raise ValueError('run inputs or evaluation tool changed during transfer check; no output published')


# This worker runs in a clean interpreter whose only SDK path is the verified
# extracted source tree. Keeping orchestration out of the archived tree avoids
# changing any file covered by the original training loader's provenance.
WORKER = '''from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import torch

request = json.loads(Path(sys.argv[1]).read_text())
def check_pins():
    for name, expected in request['pins'].items():
        path = Path(name)
        if path.is_symlink() or not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('run inputs or evaluation tool changed during transfer check')
check_pins()
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
from cartpole_sdk.learning import swing_experiment
if not Path(swing_experiment.__file__).resolve().is_relative_to(Path(request['frozen'])/'src'):
    raise ValueError('training loader was not imported from the frozen runtime')
model, recipe, selected = swing_experiment.load_trial(request['run'], request['checkpoint'])
if recipe != request['recipe'] or selected != request['selected']:
    raise ValueError('archived loader returned different recipe or checkpoint metadata')
# Resolve relative imports against the original frozen learning package.
name = 'cartpole_sdk.learning.transfer_checks'
spec = importlib.util.spec_from_file_location(name, request['evaluator'])
evaluator = importlib.util.module_from_spec(spec)
sys.modules[name] = evaluator
spec.loader.exec_module(evaluator)
weights = evaluator._weights_digest(model.policy.state_dict())
binding = dict(request['binding'], loaded_policy_weights_sha256=weights,
    evaluation_source=evaluator.source_identity())
report = evaluator.run_suite(model, recipe['experiment'], request['staged'],
    seeds=tuple(request['seeds']), seconds=request['seconds'],
    checkpoint_sha256=selected['checkpoint_sha256'], source_binding=binding)
if (report['in_memory_weights_sha256'] != weights or
        evaluator._weights_digest(model.policy.state_dict()) != weights):
    raise ValueError('evaluated policy weights differ from the loaded checkpoint')
name = 'cartpole_sdk.learning.candidate_parity'
spec = importlib.util.spec_from_file_location(name, request['parity_evaluator'])
parity = importlib.util.module_from_spec(spec)
sys.modules[name] = parity
spec.loader.exec_module(parity)
if parity.model_weights_sha256(model) != weights:
    raise ValueError('parity input weights differ from the loaded checkpoint')
parity_report = parity.check_candidate(model, recipe['experiment'], Path(request['staged'])/'parity',
    checkpoint_sha256=selected['checkpoint_sha256'], seeds=tuple(request['seeds']), seconds=request['seconds'])
if (parity_report['model_weights_sha256_before'] != weights or
        parity_report['model_weights_sha256_after'] != weights or
        parity.model_weights_sha256(model) != weights):
    raise ValueError('parity policy weights differ from the loaded checkpoint')
check_pins()
(Path(request['staged'])/'worker-result.json').write_text(json.dumps(dict(
    in_memory_weights_sha256=weights, evaluation_source=evaluator.source_identity(),
    parity_evaluation_source=parity.source_identity()),
    indent=2, allow_nan=False)+'\\n')
'''


def run_checks(run, output, *, seeds, seconds=25., checkpoint=None):
    """Validate immutable inputs, run in frozen source, then publish a new suite."""
    run, output = Path(run).resolve(), Path(output).absolute()
    if os.path.lexists(output):
        raise FileExistsError(output)
    output = output.resolve()
    if (not seeds or any(type(seed) is not int or seed < 0 for seed in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError('distinct nonnegative evaluation seeds required')
    if (type(seconds) not in (int, float) or not math.isfinite(seconds) or
            not .01 <= seconds <= 60 or not math.isclose(seconds*100, round(seconds*100))):
        raise ValueError('seconds must contain whole 100 Hz decisions in .01..60')
    if checkpoint is not None and (type(checkpoint) is not int or checkpoint < 0):
        raise ValueError('nonnegative checkpoint step required')
    raw_recipe, raw_report = (guards._read_file(run/name) for name in ('recipe.json','report.json'))
    recipe, report = json.loads(raw_recipe), json.loads(raw_report)
    if (recipe.get('schema') != SCHEMA or sha256(raw_recipe).hexdigest() != report.get('recipe_sha256')
            or any(report.get(key) != value for key,value in recipe.items())):
        raise ValueError('recipe hash or report metadata mismatch')
    demonstration = recipe['demonstrations']
    used = set(recipe['training_seeds']+recipe['evaluation_seeds'])
    if demonstration is not None:
        used.update(demonstration['train_episodes']+demonstration['validation_episodes'])
    if set(seeds) & used:
        raise ValueError('evaluation seed overlap with training, development or demonstration poses')
    source_path = run/'source.zip'
    if source_path.stat().st_size > guards.MAX_ARCHIVE_BYTES:
        raise ValueError('source archive exceeds size limit')
    source = guards._read_file(source_path)
    if sha256(source).hexdigest() != report.get('source_zip_sha256'):
        raise ValueError('source archive hash mismatch')
    evaluations = report.get('evaluations', [])
    selected = (evaluations[-1] if evaluations else None) if checkpoint is None else next(
        (row for row in evaluations if row.get('steps') == checkpoint), None)
    if selected is None:
        raise ValueError('checkpoint not found')
    cp = PurePosixPath(selected['checkpoint'])
    if (len(cp.parts) != 2 or cp.parts[0] != 'checkpoints' or cp.suffix != '.zip'
            or '\\' in str(cp) or (run/'checkpoints').is_symlink()):
        raise ValueError('checkpoint path mismatch')
    checkpoint_path = run/cp
    checkpoint_sha = sha256(guards._read_file(checkpoint_path)).hexdigest()
    if checkpoint_sha != selected.get('checkpoint_sha256'):
        raise ValueError('checkpoint hash mismatch')
    pins = {str(run/'recipe.json'):sha256(raw_recipe).hexdigest(),
        str(run/'report.json'):sha256(raw_report).hexdigest(),
        str(source_path):sha256(source).hexdigest(), str(checkpoint_path):checkpoint_sha}
    demonstration_sha = None
    if demonstration is not None:
        path = run/'demonstrations.npz'
        demonstration_sha = sha256(guards._read_file(path)).hexdigest()
        if demonstration_sha != demonstration['sha256']:
            raise ValueError('demonstration hash mismatch')
        pins[str(path)] = demonstration_sha
    evaluator = guards._read_file(EVALUATOR_PATH)
    parity_evaluator = guards._read_file(PARITY_PATH)
    pins[str(EVALUATOR_PATH)] = sha256(evaluator).hexdigest()
    pins[str(PARITY_PATH)] = sha256(parity_evaluator).hexdigest()
    for path in (Path(__file__), GUARDS_PATH):
        pins[str(path)] = sha256(guards._read_file(path)).hexdigest()
    binding = dict(schema='cartpole-swing-transfer-binding-v1', run=str(run), run_schema=SCHEMA,
        recipe_sha256=pins[str(run/'recipe.json')], report_sha256=pins[str(run/'report.json')],
        source_zip_sha256=pins[str(source_path)], checkpoint_sha256=checkpoint_sha,
        checkpoint_steps=selected['steps'], demonstrations_sha256=demonstration_sha,
        training_source_provenance=recipe['provenance'], evaluator_source_path=str(EVALUATOR_PATH),
        evaluator_sha256=sha256(evaluator).hexdigest(), runner_sha256=pins[str(Path(__file__))],
        parity_evaluator_source_path=str(PARITY_PATH), parity_evaluator_sha256=sha256(parity_evaluator).hexdigest(),
        archive_guards_sha256=pins[str(GUARDS_PATH)], worker_sha256=sha256(WORKER.encode()).hexdigest())
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        members = guards._archive_members(archive, SCHEMA)
        with tempfile.TemporaryDirectory(prefix='cartpole-swing-transfer-') as directory:
            temporary = Path(directory).resolve()
            frozen, tool, staged = temporary/'training', temporary/'tool', temporary/'result'
            frozen.mkdir(); tool.mkdir()
            for member in members:
                destination = frozen/member.filename
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('xb') as stream:
                        stream.write(archive.read(member))
            evaluator_path = tool/'transfer_checks.py'
            evaluator_path.write_bytes(evaluator)
            parity_path = tool/'candidate_parity.py'
            parity_path.write_bytes(parity_evaluator)
            # source_identity() hashes a sibling diagnostics.py. Supply the exact
            # frozen imported helper bytes, without modifying the training tree.
            (tool/'diagnostics.py').write_bytes(guards._read_file(frozen/'src/cartpole_sdk/learning/diagnostics.py'))
            worker_path = tool/'worker.py'; worker_path.write_text(WORKER)
            request_path = tool/'request.json'
            request = dict(run=str(run), frozen=str(frozen), staged=str(staged), evaluator=str(evaluator_path),
                parity_evaluator=str(parity_path),
                recipe=recipe, selected=selected, checkpoint=selected['steps'], seeds=list(seeds),
                seconds=float(seconds), binding=binding, pins=pins)
            request_path.write_text(json.dumps(request, indent=2, allow_nan=False)+'\n')
            environment = dict(os.environ, PYTHONPATH=str(frozen/'src'), PYTHONNOUSERSITE='1',
                PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                MKL_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
            environment.pop('PYTHONHOME', None)
            command = [sys.executable, str(worker_path), str(request_path)]
            subprocess.run(command, cwd=frozen, env=environment, check=True)
            _check_pins(pins)
            receipt = json.loads(guards._read_file(staged/'worker-result.json'))
            suite_report = guards._read_file(staged/'report.json')
            suite_recipe = guards._read_file(staged/'recipe.json')
            parity_report = guards._read_file(staged/'parity/report.json')
            parity_recipe = guards._read_file(staged/'parity/recipe.json')
            provenance = dict(binding, schema='cartpole-swing-transfer-replay-v1',
                in_memory_weights_sha256=receipt['in_memory_weights_sha256'],
                evaluation_source=receipt['evaluation_source'], suite_report_sha256=sha256(suite_report).hexdigest(),
                parity_evaluation_source=receipt['parity_evaluation_source'],
                parity_report_sha256=sha256(parity_report).hexdigest(), parity_recipe_sha256=sha256(parity_recipe).hexdigest(),
                suite_recipe_sha256=sha256(suite_recipe).hexdigest(), seeds=list(seeds), seconds=float(seconds),
                frozen_runtime_directory=str(frozen), python_executable=sys.executable, command=command,
                hardware_accepted=False, deployable=False,
                note='Original archived load_trial guards remain enabled. Current evaluator uses frozen training runtime; temporary source was removed.')
            (staged/'evaluation-tool.py').write_bytes(evaluator)
            (staged/'parity/evaluation-tool.py').write_bytes(parity_evaluator)
            (staged/'transfer-provenance.json').write_text(json.dumps(provenance, indent=2, allow_nan=False)+'\n')
            shutil.copytree(staged, output)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--seconds', type=float, default=25.)
    parser.add_argument('--checkpoint', type=int)
    args = parser.parse_args()
    try:
        result = run_checks(args.run, args.output, seeds=args.seeds, seconds=args.seconds, checkpoint=args.checkpoint)
        print(json.dumps(dict(output=str(args.output.resolve()), checkpoint_steps=result['checkpoint_steps'],
            checkpoint_sha256=result['checkpoint_sha256'], in_memory_weights_sha256=result['in_memory_weights_sha256'])))
    except subprocess.CalledProcessError as error:
        parser.exit(error.returncode if error.returncode > 0 else 1, 'frozen transfer evaluation failed\n')
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(2, str(error)+'\n')


if __name__ == '__main__':
    main()
