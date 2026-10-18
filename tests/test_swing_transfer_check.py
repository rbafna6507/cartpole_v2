"""Frozen training code and the current stress evaluator retain separate bindings."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from test_replay_balance_evaluation import fixture_run, write_json

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'examples/swing_transfer_check.py'


def api():
    assert SCRIPT.exists(), 'frozen swing transfer command missing'
    spec = importlib.util.spec_from_file_location('swing_transfer_check', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def trained_run(tmp_path_factory):
    pytest.importorskip('stable_baselines3')
    from test_ppo_training import make_experiment
    from cartpole_sdk.learning.swing_experiment import run_trial
    base = tmp_path_factory.mktemp('frozen-swing-transfer')
    run = base/'run'
    run_trial(make_experiment(base), run, initialization='scratch', seed=3, steps=8, every=8,
        training_seeds=(31,), evaluation_seeds=(301,), evaluation_seconds=.01,
        n_steps=8, batch_size=4, epochs=1)
    # A semantics-preserving historical source variant ensures the live loader
    # rejects this fixture, so a successful suite must use the archived loader.
    source = run/'source.zip'
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    name = 'src/cartpole_sdk/learning/swing_experiment.py'
    members[name] += b'\n# Historical source variant for frozen-runtime integration.\n'
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)
    recipe = json.loads((run/'recipe.json').read_text())
    recipe['provenance']['swing_experiment_sha256'] = sha256(
        members['src/cartpole_sdk/learning/swing_experiment.py']).hexdigest()
    write_json(run/'recipe.json', recipe)
    report = json.loads((run/'report.json').read_text())
    report.update(recipe, recipe_sha256=sha256((run/'recipe.json').read_bytes()).hexdigest(),
        source_zip_sha256=sha256(source.read_bytes()).hexdigest())
    write_json(run/'report.json', report)
    return run


@pytest.mark.parametrize('checkpoint',[None,0])
def test_actual_frozen_loader_current_evaluator_and_policy_weights_are_bound(tmp_path,trained_run,checkpoint):
    m = api()
    from cartpole_sdk.learning.swing_experiment import load_trial
    from cartpole_sdk.learning.transfer_checks import _weights_digest
    from stable_baselines3 import PPO
    with pytest.raises(ValueError, match='source/dependency'):
        load_trial(trained_run)
    before = {p:p.read_bytes() for p in trained_run.rglob('*') if p.is_file()}
    output = tmp_path/'suite'
    provenance = m.run_checks(trained_run, output, seeds=(701,), seconds=.01, checkpoint=checkpoint)
    report = json.loads((output/'report.json').read_text())
    recipe = json.loads((output/'recipe.json').read_text())
    selected = 8 if checkpoint is None else checkpoint
    checkpoint_path = trained_run/'checkpoints'/f'step-{selected:09d}.zip'
    actual = PPO.load(checkpoint_path, device='cpu')
    assert provenance['checkpoint_steps'] == selected
    assert provenance['checkpoint_sha256'] == sha256(checkpoint_path.read_bytes()).hexdigest()
    assert provenance['in_memory_weights_sha256'] == _weights_digest(actual.policy.state_dict())
    assert report['in_memory_weights_sha256'] == provenance['in_memory_weights_sha256']
    assert recipe['source_binding']['loaded_policy_weights_sha256'] == provenance['in_memory_weights_sha256']
    assert provenance['training_source_provenance'] == json.loads((trained_run/'recipe.json').read_text())['provenance']
    tool = ROOT/'src/cartpole_sdk/learning/transfer_checks.py'
    assert provenance['evaluator_sha256'] == sha256(tool.read_bytes()).hexdigest()
    assert (output/'evaluation-tool.py').read_bytes() == tool.read_bytes()
    assert report['evaluation_source']['evaluator_sha256'] == provenance['evaluator_sha256']
    parity_tool = ROOT/'src/cartpole_sdk/learning/candidate_parity.py'
    parity = json.loads((output/'parity/report.json').read_text())
    assert provenance['parity_evaluator_sha256'] == sha256(parity_tool.read_bytes()).hexdigest()
    assert (output/'parity/evaluation-tool.py').read_bytes() == parity_tool.read_bytes()
    assert provenance['parity_report_sha256'] == sha256((output/'parity/report.json').read_bytes()).hexdigest()
    assert parity['checkpoint_sha256'] == provenance['checkpoint_sha256']
    assert parity['model_weights_sha256_before'] == provenance['in_memory_weights_sha256']
    assert parity['model_weights_sha256_after'] == provenance['in_memory_weights_sha256']
    assert parity['emission_parity_pass'] and parity['compared_actions'] == 2
    assert parity['evaluation_source']['runtime'] == report['evaluation_source']['runtime']
    assert provenance['suite_report_sha256'] == sha256((output/'report.json').read_bytes()).hexdigest()
    assert len(report['episodes']) == 22 and report['completed']
    assert all(p.read_bytes() == raw for p,raw in before.items())
    assert not Path(provenance['frozen_runtime_directory']).exists()


@pytest.mark.parametrize('seed',[11,101,21,22])
def test_training_development_and_demo_pose_overlap_rejected_without_output(tmp_path,seed):
    m = api(); run = fixture_run(tmp_path, family='swing', demonstration=b'demo fixture')
    output = tmp_path/'never-created'
    with pytest.raises(ValueError, match='overlap'):
        m.run_checks(run, output, seeds=(seed,), seconds=.01)
    assert not output.exists()


@pytest.mark.parametrize('corruption',['recipe','report','source','checkpoint','demonstration'])
def test_corrupt_frozen_bindings_rejected_before_worker(tmp_path,corruption):
    m = api(); run = fixture_run(tmp_path, family='swing', demonstration=b'demo fixture')
    paths = {'recipe':'recipe.json', 'report':'report.json', 'source':'source.zip',
        'checkpoint':'checkpoints/step-000000016.zip', 'demonstration':'demonstrations.npz'}
    path = run/paths[corruption]
    if corruption == 'report':
        report = json.loads(path.read_text()); report['optimizer_seed'] = 999; write_json(path,report)
    else:
        path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='hash|metadata'):
        m.run_checks(run,tmp_path/'never-created',seeds=(701,),seconds=.01)
    assert not (tmp_path/'never-created').exists()


@pytest.mark.parametrize('member',['../escaped.py','src/sitecustomize.py'])
def test_transfer_uses_replay_archive_path_allowlist(tmp_path,member):
    m = api(); run = fixture_run(tmp_path,family='swing',extra_members=((member,'pass'),))
    with pytest.raises(ValueError, match='archive|member'):
        m.run_checks(run,tmp_path/'never-created',seeds=(701,),seconds=.01)
    assert not (tmp_path/'never-created').exists()


@pytest.mark.parametrize('changed',['recipe.json','report.json','source.zip',
    'checkpoints/step-000000008.zip','demonstrations.npz'])
def test_changed_input_after_worker_is_not_published(tmp_path,trained_run,monkeypatch,changed):
    m = api(); run = tmp_path/'run'; shutil.copytree(trained_run,run)
    if changed == 'demonstrations.npz':
        (run/changed).write_bytes(b'hashed demo fixture')
        recipe = json.loads((run/'recipe.json').read_text())
        recipe['demonstrations'] = dict(sha256=sha256((run/changed).read_bytes()).hexdigest(),
            train_episodes=[401], validation_episodes=[402], updates=1)
        write_json(run/'recipe.json',recipe)
        report = json.loads((run/'report.json').read_text())
        report.update(recipe,recipe_sha256=sha256((run/'recipe.json').read_bytes()).hexdigest())
        write_json(run/'report.json',report)
    original = m.subprocess.run
    def run_then_change(*args,**kwargs):
        result = original(*args,**kwargs)
        path = run/changed; path.write_bytes(path.read_bytes()+b' ')
        return result
    monkeypatch.setattr(m.subprocess,'run',run_then_change)
    with pytest.raises(ValueError,match='changed during'):
        m.run_checks(run,tmp_path/'never-published',seeds=(701,),seconds=.01)
    assert not (tmp_path/'never-published').exists()


@pytest.mark.parametrize('module_path',['EVALUATOR_PATH','PARITY_PATH'])
def test_evaluator_change_after_worker_is_not_published(tmp_path,trained_run,monkeypatch,module_path):
    m = api(); tool=tmp_path/getattr(m,module_path).name;tool.write_bytes(getattr(m,module_path).read_bytes())
    monkeypatch.setattr(m,module_path,tool)
    original = m.subprocess.run
    def run_then_change(*args,**kwargs):
        result = original(*args,**kwargs)
        tool.write_bytes(tool.read_bytes()+b'\n# changed evaluator\n')
        return result
    monkeypatch.setattr(m.subprocess,'run',run_then_change)
    with pytest.raises(ValueError,match='changed during'):
        m.run_checks(trained_run,tmp_path/'never-published',seeds=(701,),seconds=.01)
    assert not (tmp_path/'never-published').exists()


def test_existing_or_dangling_output_is_preserved(tmp_path):
    m = api();run = fixture_run(tmp_path,family='swing')
    output=tmp_path/'existing';output.mkdir();(output/'sentinel').write_text('keep')
    with pytest.raises(FileExistsError):m.run_checks(run,output,seeds=(701,),seconds=.01)
    assert (output/'sentinel').read_text()=='keep'
    dangling=tmp_path/'dangling';dangling.symlink_to(tmp_path/'missing')
    with pytest.raises(FileExistsError):m.run_checks(run,dangling,seeds=(701,),seconds=.01)
    assert dangling.is_symlink()


@pytest.mark.parametrize('limit',['MAX_ARCHIVE_BYTES','MAX_MEMBER_BYTES','MAX_EXTRACTED_BYTES'])
def test_transfer_retains_replay_size_guards(tmp_path,monkeypatch,limit):
    m = api();run = fixture_run(tmp_path,family='swing')
    monkeypatch.setattr(m.guards,limit,1)
    with pytest.raises(ValueError,match='size limit'):
        m.run_checks(run,tmp_path/'never-created',seeds=(701,),seconds=.01)
    assert not (tmp_path/'never-created').exists()


def test_archived_source_guard_failure_propagates_without_output(tmp_path,trained_run):
    m = api(); run = tmp_path/'run'; shutil.copytree(trained_run,run)
    recipe = json.loads((run/'recipe.json').read_text())
    recipe['provenance']['swing_experiment_sha256'] = '0'*64
    write_json(run/'recipe.json',recipe)
    report = json.loads((run/'report.json').read_text())
    report.update(recipe,recipe_sha256=sha256((run/'recipe.json').read_bytes()).hexdigest())
    write_json(run/'report.json',report)
    with pytest.raises(subprocess.CalledProcessError):
        m.run_checks(run,tmp_path/'never-created',seeds=(701,),seconds=.01)
    assert not (tmp_path/'never-created').exists()


def test_offline_wrapper_runs_from_an_unrelated_directory(tmp_path,trained_run):
    api(); wrapper=ROOT/'scripts/swing-transfer-check'
    assert wrapper.exists(), 'offline swing transfer wrapper missing'
    output=tmp_path/'cli-suite'
    process=subprocess.run([str(wrapper),str(trained_run),'--output',str(output),
        '--seeds','701','--seconds','.01'],cwd=tmp_path,text=True,capture_output=True)
    assert process.returncode==0,process.stderr
    assert (output/'report.json').is_file()
    assert (output/'transfer-provenance.json').is_file()
