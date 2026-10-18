import subprocess
import sys
from pathlib import Path
import pytest
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def test_summary_rejects_different_constraints_and_teacher_recipes(tmp_path):
    from cartpole_sdk.learning.balance_experiment import run_trial
    exp=make_experiment(tmp_path)
    common=dict(steps=8,every=8,n_steps=8,batch_size=4,epochs=1,
        training_seeds=(11,),evaluation_seeds=(101,),evaluation_seconds=.05,imitation_updates=1)
    gains=dict(position_gain=1.,velocity_gain=2.,theta_gain=40.,omega_gain=2.)
    a=tmp_path/'a';b=tmp_path/'b';c=tmp_path/'c'
    run_trial(exp,a,initialization='teacher',seed=3,gains=gains,**common)
    run_trial(exp,b,initialization='teacher',seed=17,gains=gains,constraint='equilibrium',**common)
    run_trial(exp,c,initialization='teacher',seed=17,gains=dict(gains,position_gain=9.),**common)
    script=Path(__file__).parents[1]/'evidence/rl-balance-20261018/tools/summarize.py'
    for other in (b,c):
        result=subprocess.run([sys.executable,str(script),str(a),str(other),'--output',str(tmp_path/(other.name+'-summary'))],capture_output=True,text=True)
        assert result.returncode!=0, 'incomparable runs accepted as a matched comparison'
        assert 'incomparable' in result.stderr
