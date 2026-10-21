"""Regression for preserving faulted episodes in the research evaluator."""
import importlib.util
import json
from pathlib import Path
import pytest


def test_early_fault_is_saved_with_unavailable_final_window_metrics(tmp_path):
    pytest.importorskip('torch')
    from cartpole_sdk.learning.error_training import load_profile
    from cartpole_sdk.learning.ppo import TrainingEnv
    from cartpole_sdk.learning.projected_ppo import EquilibriumPPO
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('confidence_driver',root/'evidence/policy-confidence-20261021/run-joint-stage-v2.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    experiment,_=load_profile(root/'training/profiles/rl-encoder-20261021',seconds=10.)
    experiment['observation_config']['dropout_probability']=1.
    env=TrainingEnv(experiment,(880001,))
    try:
        model=EquilibriumPPO('MultiInputPolicy',env,seed=3,n_steps=8,batch_size=4,n_epochs=1,device='cpu')
        report=module.evaluate(model,experiment,tmp_path/'evaluation',[880002],10.,'0'*64)
    finally:env.close()
    saved=json.loads((tmp_path/'evaluation/report.json').read_text())
    assert saved==report
    assert report['completed']
    assert len(report['episodes'])==2
    for episode in report['episodes']:
        assert episode['fault_reason']
        assert episode['hold_success'] is False
        assert episode['final_window_complete'] is False
        assert episode['tail_theta_rms_deg'] is None
        assert episode['final_window_x_rms_m'] is None
    assert all(row['faults']==1 for row in report['summary'])
