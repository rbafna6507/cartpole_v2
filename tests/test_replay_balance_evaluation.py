"""Replay frozen source without importing or modifying the current learner."""
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import warnings
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'examples/replay_balance_evaluation.py'
ARCHIVED_CLI = '''import json, os, sys
from pathlib import Path
from cartpole_sdk.learning import balance_experiment
args=sys.argv[1:]
assert args[0] == 'evaluate'
output=Path(args[args.index('--output')+1])
output.mkdir(parents=True, exist_ok=False)
(output/'evaluation.json').write_text(json.dumps(dict(
    argv=args, python=sys.executable, cwd=os.getcwd(),
    pythonpath=os.environ['PYTHONPATH'], imported_from=balance_experiment.__file__,
    marker=balance_experiment.MARKER)))
'''


def api():
    assert SCRIPT.exists(), 'frozen-source replay runner missing'
    spec=importlib.util.spec_from_file_location('balance_replay',SCRIPT)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    path.write_text(json.dumps(value))


def fixture_run(tmp_path, *, cli=ARCHIVED_CLI, extra_members=(), family='balance', demonstration=None):
    run=tmp_path/'run'; run.mkdir()
    cp=run/'checkpoints'/'step-000000016.zip'; cp.parent.mkdir(); cp.write_bytes(b'fake checkpoint for subprocess contract')
    recipe=dict(schema=f'cartpole-{family}-learning-v1', initialization='teacher',
        optimizer_seed=3, training_seeds=[11], evaluation_seeds=[101],
        steps=16, provenance={'fixture':True})
    if family=='swing':
        recipe['demonstrations']=None
        if demonstration is not None:
            (run/'demonstrations.npz').write_bytes(demonstration)
            recipe['demonstrations']={'sha256':sha256(demonstration).hexdigest(),
                'train_episodes':[21], 'validation_episodes':[22], 'updates':1}
    write_json(run/'recipe.json',recipe)
    with zipfile.ZipFile(run/'source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('examples/balance_learning.py',cli)
        archive.writestr('src/cartpole_sdk/__init__.py','')
        archive.writestr('src/cartpole_sdk/learning/__init__.py','')
        archive.writestr('src/cartpole_sdk/learning/balance_experiment.py',"MARKER = 'frozen fixture'\n")
        if family=='swing':
            archive.writestr('examples/swing_learning.py',cli.replace('balance_experiment','swing_experiment'))
            archive.writestr('scripts/swing-learning','#!/bin/sh\n')
            archive.writestr('src/cartpole_sdk/learning/swing_experiment.py',"MARKER = 'frozen swing fixture'\n")
        for name,contents in extra_members:
            archive.writestr(name,contents)
    report=dict(recipe, completed=True,
        recipe_sha256=sha256((run/'recipe.json').read_bytes()).hexdigest(),
        source_zip_sha256=sha256((run/'source.zip').read_bytes()).hexdigest(),
        evaluations=[dict(steps=16,checkpoint='checkpoints/'+cp.name,checkpoint_sha256=sha256(cp.read_bytes()).hexdigest())])
    write_json(run/'report.json',report)
    return run


@pytest.mark.parametrize('demonstration',[None,b'frozen observed demonstration fixture'])
def test_swing_replay_dispatches_frozen_cli_and_records_demonstration_binding(tmp_path,demonstration):
    m=api();run=fixture_run(tmp_path,family='swing',demonstration=demonstration)
    output=tmp_path/'swing-evaluation'
    result=m.replay(run,output,seeds=(102,),seconds=.01,starts=('hanging','upright'))
    observed=json.loads((output/'evaluation.json').read_text())
    assert observed['marker']=='frozen swing fixture'
    assert Path(result['command'][1]).name=='swing_learning.py'
    assert result['run_schema']=='cartpole-swing-learning-v1'
    assert result['demonstrations_sha256']==(None if demonstration is None else sha256(demonstration).hexdigest())
    assert not Path(observed['cwd']).exists()


@pytest.mark.parametrize('corruption',['bytes','symlink','missing'])
def test_swing_demonstration_binding_checked_before_execution(tmp_path,corruption):
    m=api();run=fixture_run(tmp_path,family='swing',demonstration=b'original')
    data=run/'demonstrations.npz';data.unlink()
    if corruption=='bytes':data.write_bytes(b'changed')
    if corruption=='symlink':
        elsewhere=tmp_path/'elsewhere.npz';elsewhere.write_bytes(b'original');data.symlink_to(elsewhere)
    output=tmp_path/'never-created'
    with pytest.raises((ValueError,OSError),match='demonstration|regular input'):
        m.replay(run,output,seeds=(102,),seconds=.01)
    assert not output.exists()


def test_swing_demonstration_mutation_during_evaluation_blocks_success_provenance(tmp_path):
    cli=ARCHIVED_CLI+"\n(Path(args[1])/'demonstrations.npz').write_bytes(b'changed during evaluation')\n"
    m=api();run=fixture_run(tmp_path,family='swing',demonstration=b'original',cli=cli)
    output=tmp_path/'evaluation'
    with pytest.raises(ValueError,match='changed during replay'):
        m.replay(run,output,seeds=(102,),seconds=.01)
    assert (output/'evaluation.json').exists()
    assert not (output/'replay-provenance.json').exists()


@pytest.mark.parametrize('missing',['examples/swing_learning.py','src/cartpole_sdk/learning/swing_experiment.py'])
def test_swing_replay_requires_the_corresponding_frozen_evaluator(tmp_path,missing):
    m=api();run=fixture_run(tmp_path,family='swing')
    archive_path=run/'source.zip'
    with zipfile.ZipFile(archive_path) as archive:
        members={name:archive.read(name) for name in archive.namelist() if name!=missing}
    with zipfile.ZipFile(archive_path,'w') as archive:
        for name,contents in members.items():archive.writestr(name,contents)
    report=json.loads((run/'report.json').read_text())
    report['source_zip_sha256']=sha256(archive_path.read_bytes()).hexdigest()
    write_json(run/'report.json',report)
    with pytest.raises(ValueError,match='frozen swing evaluator'):
        m.replay(run,tmp_path/'never-created',seeds=(102,),seconds=.01)
    assert not (tmp_path/'never-created').exists()


def test_replay_uses_only_frozen_imports_current_python_and_records_bindings(tmp_path, monkeypatch):
    m=api(); run=fixture_run(tmp_path); output=tmp_path/'new-evaluation'
    monkeypatch.setenv('PYTHONPATH','/must/not/be/inherited')
    before={p:p.read_bytes() for p in run.rglob('*') if p.is_file()}
    result=m.replay(run,output,seeds=(102,103),seconds=25.,checkpoint=16,starts=('upright','hanging'))
    observed=json.loads((output/'evaluation.json').read_text())
    assert observed['marker']=='frozen fixture'
    assert observed['argv']==['evaluate',str(run.resolve()),'--output',str(output.resolve()),
        '--seeds','102','103','--seconds','25.0','--starts','upright','hanging','--checkpoint','16']
    assert observed['python']==sys.executable
    assert Path(observed['imported_from']).is_relative_to(Path(observed['pythonpath']))
    assert observed['pythonpath']==str(Path(observed['cwd'])/'src')
    assert not Path(observed['cwd']).exists(), 'temporary frozen source must be removed'
    assert result==json.loads((output/'replay-provenance.json').read_text())
    assert result['source_zip_sha256']==sha256((run/'source.zip').read_bytes()).hexdigest()
    assert result['report_sha256']==sha256((run/'report.json').read_bytes()).hexdigest()
    assert result['evaluation_sha256']==sha256((output/'evaluation.json').read_bytes()).hexdigest()
    assert all(p.read_bytes()==content for p,content in before.items())


@pytest.mark.parametrize('family',['balance','swing'])
@pytest.mark.parametrize('corruption',['recipe','source','report_metadata','checkpoint'])
def test_corrupt_bindings_fail_before_starting_archived_evaluator(tmp_path,corruption,family):
    m=api(); run=fixture_run(tmp_path,family=family); output=tmp_path/'never-created'
    if corruption=='recipe':
        with (run/'recipe.json').open('ab') as stream:stream.write(b' ')
    elif corruption=='source':
        with (run/'source.zip').open('ab') as stream:stream.write(b'changed')
    elif corruption=='checkpoint':
        (run/'checkpoints/step-000000016.zip').write_bytes(b'changed')
    else:
        report=json.loads((run/'report.json').read_text()); report['optimizer_seed']=17
        write_json(run/'report.json',report)
    with pytest.raises(ValueError,match='hash|metadata'):
        m.replay(run,output,seeds=(102,),seconds=.01)
    assert not output.exists()


@pytest.mark.parametrize('family',['balance','swing'])
@pytest.mark.parametrize('name',['../outside.py','/absolute.py','src/cartpole_sdk/../escape.py',
    'src/cartpole_sdk/./alias.py','src\\cartpole_sdk\\escape.py','src/sitecustomize.py'])
def test_unsafe_archive_paths_are_rejected_before_execution(tmp_path,name,family):
    m=api(); run=fixture_run(tmp_path,family=family,extra_members=((name,b'unsafe'),));output=tmp_path/'never-created'
    with pytest.raises(ValueError,match='archive|member'):
        m.replay(run,output,seeds=(102,),seconds=.01)
    assert not output.exists()
    assert not (tmp_path/'outside.py').exists()


@pytest.mark.parametrize('family',['balance','swing'])
def test_archive_symlinks_and_duplicate_members_are_rejected(tmp_path,family):
    m=api()
    for kind in ('symlink','duplicate'):
        base=tmp_path/kind;base.mkdir()
        if kind=='symlink':
            member=zipfile.ZipInfo('src/cartpole_sdk/linked.py')
            member.create_system=3;member.external_attr=(stat.S_IFLNK|0o777)<<16
            extra=((member,'/tmp/elsewhere'),)
        else:
            extra=(('src/cartpole_sdk/learning/balance_experiment.py','duplicate'),)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            run=fixture_run(base,family=family,extra_members=extra)
        with pytest.raises(ValueError,match='archive|member'):
            m.replay(run,base/'never-created',seeds=(102,),seconds=.01)
        assert not (base/'never-created').exists()


def test_existing_or_dangling_output_is_never_overwritten(tmp_path):
    m=api();run=fixture_run(tmp_path)
    output=tmp_path/'existing';output.mkdir();(output/'sentinel').write_text('keep')
    with pytest.raises(FileExistsError):m.replay(run,output,seeds=(102,),seconds=.01)
    assert (output/'sentinel').read_text()=='keep'
    dangling=tmp_path/'dangling';dangling.symlink_to(tmp_path/'missing')
    with pytest.raises(FileExistsError):m.replay(run,dangling,seeds=(102,),seconds=.01)
    assert dangling.is_symlink()


def test_archived_evaluator_failure_is_propagated_without_success_manifest(tmp_path):
    m=api();run=fixture_run(tmp_path,cli='raise SystemExit(23)\n');output=tmp_path/'failed'
    with pytest.raises(subprocess.CalledProcessError) as error:
        m.replay(run,output,seeds=(102,),seconds=.01)
    assert error.value.returncode==23
    assert not output.exists()


def test_cli_and_wrapper_evaluate_without_network_or_environment_installation(tmp_path):
    api();run=fixture_run(tmp_path);output=tmp_path/'cli-output'
    wrapper=ROOT/'scripts/replay-balance-evaluation'
    assert wrapper.exists(), 'offline replay wrapper missing'
    process=subprocess.run([str(wrapper),str(run),'--output',str(output),'--seeds','102',
        '--seconds','.01'],cwd=tmp_path,text=True,capture_output=True)
    assert process.returncode==0,process.stderr
    assert (output/'evaluation.json').is_file()
    assert (output/'replay-provenance.json').is_file()


def test_unknown_schema_is_rejected_even_with_valid_hashes(tmp_path):
    m=api();run=fixture_run(tmp_path,family='unknown')
    with pytest.raises(ValueError,match='metadata'):
        m.replay(run,tmp_path/'never-created',seeds=(102,),seconds=.01)
    assert not (tmp_path/'never-created').exists()


@pytest.mark.parametrize('family',['balance','swing'])
@pytest.mark.parametrize('limit',['MAX_ARCHIVE_BYTES','MAX_MEMBER_BYTES','MAX_EXTRACTED_BYTES'])
def test_source_size_limits_apply_to_every_evaluator(tmp_path,monkeypatch,family,limit):
    m=api();run=fixture_run(tmp_path,family=family)
    monkeypatch.setattr(m,limit,1)
    with pytest.raises(ValueError,match='size limit'):
        m.replay(run,tmp_path/'never-created',seeds=(102,),seconds=.01)
    assert not (tmp_path/'never-created').exists()
