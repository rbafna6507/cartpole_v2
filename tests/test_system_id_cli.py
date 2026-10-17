"""Executable operator CLI behavior, including an outside-repository launcher."""
from dataclasses import asdict
import json,os,subprocess,sys
from pathlib import Path
from unittest.mock import patch
import pytest
from cartpole_sdk.sim.config import SimulationConfig

ROOT=Path(__file__).resolve().parents[1]

def cli():
    from cartpole_sdk.identification.cli import main
    return main


def test_help_and_offline_templates_never_open_hardware(tmp_path,capsys):
    with patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('hardware opened')):
        assert cli()([])==0
        assert 'collect-pulse' in capsys.readouterr().out
        for args in (['--help'],['collect-pulse','--help'],['fit-passive','--help']):
            with pytest.raises(SystemExit) as caught:cli()(args)
            assert caught.value.code==0
        out=tmp_path/'assumptions.json'
        assert cli()(['assumptions-template','--output',str(out)])==0
        data=json.loads(out.read_text());assert data['simulation_config']['control_steps']==10
        assert set(data['simulation_config'])==set(asdict(SimulationConfig()))
        assert not data['rationale']


def test_pulse_requires_execute_and_all_hardware_outputs_are_new(tmp_path):
    with patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('hardware opened')):
        with pytest.raises(SystemExit) as caught:
            cli()(['collect-pulse','--port','offline','--output',str(tmp_path/'motion'),'--amplitude-mm','5'])
        assert caught.value.code==2 and not (tmp_path/'motion').exists()
        (tmp_path/'old').mkdir();(tmp_path/'old'/'keep').write_text('original')
        assert cli()(['collect-pulse','--execute','--port','offline','--output',str(tmp_path/'old'),'--amplitude-mm','5','--no-camera'])==2
        assert (tmp_path/'old'/'keep').read_text()=='original'


def test_launcher_from_unrelated_directory_preserves_arguments(tmp_path):
    # Substitute uv only: exercise the real shell launcher's path resolution and
    # Python module, without fetching packages or requiring a network.
    fake=tmp_path/'uv';capture=tmp_path/'uv-args.json'
    fake.write_text('#!'+sys.executable+'\nimport os,sys,json\nfrom pathlib import Path\nargs=sys.argv[1:]\nPath(os.environ["CAPTURE_ARGS"]).write_text(json.dumps(args))\nproject=args[args.index("--project")+1]\nos.environ["PYTHONPATH"]=str(Path(project)/"src")\nidx=args.index("-m")\nos.execv(sys.executable,[sys.executable,*args[idx:]])\n')
    fake.chmod(0o755)
    env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],CAPTURE_ARGS=str(capture))
    result=subprocess.run([str(ROOT/'scripts/system-id'),'--help'],cwd=tmp_path,env=env,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert 'fit-passive' in result.stdout
    args=json.loads(capture.read_text());assert Path(args[args.index('--project')+1]).samefile(ROOT)
    assert args[-1]=='--help'


def test_rejected_fit_report_is_preserved_without_export(tmp_path):
    from test_system_id_workflow import raw_recording
    train=tmp_path/'train.jsonl';valid=tmp_path/'valid.jsonl'
    ta=raw_recording(train,7);va=raw_recording(valid,8,length=.32)
    out=tmp_path/'rejected.json'
    assert cli()(['fit-passive','--training',str(train),'--training-annotations',str(ta),
        '--validation',str(valid),'--validation-annotations',str(va),'--output',str(out)])==2
    report=json.loads(out.read_text());assert report['accepted'] is False
    assert report['recommended_model'] is None and report['reasons']
    assumptions=tmp_path/'a.json';assumptions.write_text(json.dumps(dict(simulation_config=asdict(SimulationConfig()),rationale='assumed')))
    assert cli()(['export-model','--report',str(out),'--scope','passive-down','--assumptions',str(assumptions),'--output',str(tmp_path/'model.json')])==2
    assert not (tmp_path/'model.json').exists()


def test_real_exported_gym_model_runs_at_explicit_100hz(tmp_path):
    pytest.importorskip('mujoco');pytest.importorskip('gymnasium')
    from cartpole_sdk.identification.workflow import export_model
    report=dict(accepted=True,kind='passive',model='viscous',acceptance_scope='passive-down-conditional',
        parameters=dict(effective_length_m=.18,angular_damping_per_s=.65,coulomb_rad_per_s2=0.,angle_offset_rad=-.09))
    path=tmp_path/'model.json';export_model(report,scope='passive-down',output=path,
        assumptions=dict(simulation_config=asdict(SimulationConfig(control_steps=10)),rationale='Explicit assumed masses and force.'))
    out=tmp_path/'smoke.json'
    assert cli()(['gym-smoke','--model',str(path),'--steps','20','--output',str(out)])==0
    result=json.loads(out.read_text());assert result['control_interval_s']==.01
    assert result['completed_steps']==20 and result['force_saturated'] is False


def test_cli_forwards_explicit_short_hold_and_rejects_out_of_range(tmp_path):
    from cartpole_sdk.identification.cli import parser
    args=parser().parse_args(['collect-pulse','--execute','--port','offline','--output',str(tmp_path/'run'),
        '--amplitude-mm','5','--hold-seconds','3'])
    assert args.hold_seconds==3.
    with patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('invalid duration opened serial')):
        assert cli()(['collect-pulse','--execute','--port','offline','--output',str(tmp_path/'invalid'),
            '--amplitude-mm','5','--hold-seconds','2','--no-camera'])==2


@pytest.mark.parametrize('mode',('help','hardware'))
def test_hardware_and_help_do_not_require_simulation_extras(tmp_path,mode):
    blocked=['mujoco','gymnasium']+(['numpy'] if mode=='help' else [])
    code='''import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in BLOCKED:raise AssertionError('unexpected optional import: '+fullname)
sys.meta_path.insert(0,Block())
'''.replace('BLOCKED',repr(blocked))
    if mode=='hardware':code+='import cartpole_sdk.identification.experiments\n'
    else:code+='from cartpole_sdk.identification.cli import main\nassert main([])==0\n'
    result=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,env=dict(os.environ,PYTHONPATH=str(ROOT/'src')),capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_accepted_cli_fit_preserves_json_serializable_per_episode_gates(tmp_path):
    from test_system_id_workflow import raw_recording
    train=tmp_path/'train.jsonl';valid=tmp_path/'valid.jsonl'
    ta=raw_recording(train,31);va=raw_recording(valid,32,(.42,-.55,.65,-.7))
    out=tmp_path/'accepted.json'
    assert cli()(['fit-passive','--training',str(train),'--training-annotations',str(ta),
        '--validation',str(valid),'--validation-annotations',str(va),'--output',str(out)])==0
    report=json.loads(out.read_text())
    assert report['accepted'] is True
    assert all(episode['passed'] is True for episode in report['per_episode_validation'])


@pytest.mark.parametrize('static_validation',(True,False))
def test_driven_cli_requires_dynamic_validation_and_preserves_underlying_fit(tmp_path,static_validation):
    import hashlib,math
    from test_identification import trial
    def recording(name,sid,measurements):
        folder=tmp_path/name;folder.mkdir();path=folder/'rig-test.jsonl'
        rows=[dict(type='session',session=dict(session_id=str(sid),clock_id=f'board:{sid}')),
              dict(type='info',info=dict(sid=sid,firmware='executor-v6-measuredrail',encoder_upright_raw=330,home_epoch=14)),
              dict(type='ringdown_start',provenance=dict(sources={'identification/experiments.py':'a'*64}))]
        for row in measurements:
            rows.append(dict(type='state',state=dict(sid=sid,unwrapped_tick=round(row['t_s']*1000),
                unwrapped_us=round(row['t_s']*1e6),theta=row['theta_rad'],acceleration=row['cart_acceleration_m_s2'],
                mode=12,flags=207,fault=0,misses=0)))
        rows.append(dict(type='termination',error=None,records_dropped=0))
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        (folder/'report.json').write_text(json.dumps(dict(schema='cartpole-id-run-v1',raw_log=path.name,
            raw_log_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),completed=True,stop_confirmed=True,records_dropped=0,camera={})))
        return path
    training=recording('training',1,trial('training',noise=0.))
    measured=trial('validation',phase=1.1,noise=0.)
    if static_validation:
        for row in measured:row['theta_rad']=math.pi;row['cart_acceleration_m_s2']=0.
    validation=recording('validation',2,measured);out=tmp_path/'driven-fit.json'
    status=cli()(['fit-driven','--training',str(training),'--validation',str(validation),'--output',str(out)])
    assert status==(2 if static_validation else 0)
    report=json.loads(out.read_text())
    assert report['underlying_fit']['accepted'] is True
    assert report['accepted'] is (not static_validation)
    assert report['supplemental_validation']['passed'] is (not static_validation)
    assert report['parameters']==report['underlying_fit']['parameters']
    if static_validation:
        assert report['recommended_model'] is None
        assert any('validation excitation' in reason for reason in report['reasons'])
        assert report['supplemental_validation']['angle_span_rad']==0.
        assert report['supplemental_validation']['acceleration_std_m_s2']==0.


def test_review_fit_cli_forwards_frozen_sources_without_hardware(tmp_path):
    from cartpole_sdk.identification import fit_review
    out=tmp_path/'fit-review'
    with patch.object(fit_review,'review_fit',return_value={'saved_admission':{'accepted':False},'fit_sha256':'a'*64}) as review, patch('cartpole_sdk.rig.Rig',side_effect=AssertionError('offline review opened hardware')):
        assert cli()(['review-fit','--fit','fit.json','--validation','valid.jsonl','--validation-annotations','valid-annotations.json','--output',str(out)])==0
    review.assert_called_once_with(Path('fit.json'),'valid.jsonl',Path('valid-annotations.json'),out)
