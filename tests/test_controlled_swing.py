import importlib.util
import math
import pytest
pytest.importorskip('stable_baselines3')
pytest.importorskip('mujoco')
from test_ppo_training import make_experiment
from cartpole_sdk.learning.ppo import TrainingEnv


def controlled():
    assert importlib.util.find_spec('cartpole_sdk.learning.controlled_swing'), 'controlled objective missing'
    from cartpole_sdk.learning.controlled_swing import ControlledSwingEnv
    return ControlledSwingEnv


def test_unwrapped_metrics_allow_half_turn_and_detect_repeated_turns():
    controlled()
    from cartpole_sdk.learning.controlled_swing import SwingMetrics
    m = SwingMetrics(math.pi)
    for theta in (2., 1., 0., -.2):
        m.update(theta, 0., .01)
    assert m.report()['full_rotation_excursions'] == 0
    for theta in (-2., -4., -6., -8., -10.):
        m.update(theta, .27, .01)
    r = m.report()
    assert r['full_rotation_excursions'] == 2
    assert r['unwrapped_range_rotations'] > 2
    assert r['rail_zone_dwell_s'] == pytest.approx(.05)


def test_normal_horizon_truncates_and_preserves_physics(tmp_path):
    experiment = make_experiment(tmp_path)
    base, candidate = TrainingEnv(experiment, [51]), controlled()(experiment, [51])
    try:
        for env in (base, candidate):
            env.reset(options=dict(episode_seed=51, start='upright'))
            env.core.reset(seed=1, options={'state': (0.,0.,0.,0.)})
        for _ in range(5):
            a, b = base.step([0.]), candidate.step([0.])
            assert base.core.ground_truth == candidate.core.ground_truth
        assert a[2:4] == (True, False)
        assert b[2:4] == (False, True)
        assert b[1] == pytest.approx(3.)
        assert candidate.result()['score'] == pytest.approx(3.)
        assert b[4]['episode_result'] == candidate.result()
    finally:
        base.close(); candidate.close()


def test_rail_and_speed_penalties_are_explicit():
    controlled()
    from cartpole_sdk.learning.controlled_swing import control_penalty
    assert control_penalty(x=0., omega=5., rail_half=.3) == 0.
    assert control_penalty(x=.3, omega=10., rail_half=.3) == pytest.approx(2.16)


def test_small_training_exports_reloadable_checkpoint_with_objective_and_parity(tmp_path):
    assert importlib.util.find_spec('cartpole_sdk.learning.controlled_training'), 'controlled trainer missing'
    from cartpole_sdk.learning.controlled_training import train
    from cartpole_sdk.sim.profiles import profile_experiment
    report = train(tmp_path/'run', steps=128, checkpoint_every=128, seconds=.05,
                   evaluation_seeds=[109400], n_steps=128)
    assert report['completed'] and report['steps'] == 128
    assert report['numeric_parity']['emission_parity_pass']
    import json
    manifest = json.loads((tmp_path/'run'/'checkpoints'/'step-000000128'/'manifest.json').read_text())
    assert manifest['objective']['id'] == 'controlled-swing-v1'
    assert manifest['training_recipe']['randomization']['encoder']['encoder_bias_rad'][1] > 0
    assert len(report['evaluations']) == 2
    assert (tmp_path/'run'/'actor.json').exists()


def test_checkpoint_selection_can_keep_initial_actor():
    from cartpole_sdk.learning import controlled_training as trainer
    assert hasattr(trainer,'select_checkpoint'), 'checkpoint selection missing'
    rows=[]
    for step,rail in ((0,.1),(1024,2.)):
        episode=dict(hold_success=True,fault_reason=None,full_rotation_excursions=0,
                     rail_zone_dwell_s=rail,first_one_second_capture_s=3.)
        rows.append(dict(step=step,nominal=dict(episodes=[episode]),randomized=dict(episodes=[episode])))
    assert trainer.select_checkpoint(rows)['step']==0


def test_resume_retains_optimizer_and_absolute_steps(tmp_path):
    import inspect
    from cartpole_sdk.learning import controlled_training as trainer
    assert 'resume' in inspect.signature(trainer.train).parameters, 'full state resume missing'
    first=tmp_path/'first';second=tmp_path/'second'
    trainer.train(first,steps=128,checkpoint_every=128,seconds=.05,evaluation_seeds=[109400],n_steps=128)
    report=trainer.train(second,steps=128,checkpoint_every=128,seconds=.05,evaluation_seeds=[109400],n_steps=128,
                         resume=first/'checkpoints'/'step-000000128')
    assert report['steps']==256
    assert report['resume']['optimizer_state_preserved']
    assert report['resume']['start_steps']==128
    assert report['checkpoints'][0].endswith('000000128')


def test_energy_penalty_allows_required_bottom_speed_but_penalizes_surplus():
    assert importlib.util.find_spec('cartpole_sdk.learning.energy_swing'), 'energy objective missing'
    from cartpole_sdk.learning.energy_swing import energy_penalty
    length=.1603;gravity=9.81
    bottom_speed=math.sqrt(4*gravity/length)
    assert energy_penalty(theta=math.pi,omega=bottom_speed,effective_length=length,gravity=gravity)==pytest.approx(0.)
    assert energy_penalty(theta=0.,omega=bottom_speed,effective_length=length,gravity=gravity)>0


def test_confirmation_seeds_cannot_be_used_for_checkpoint_selection(tmp_path):
    from cartpole_sdk.learning.controlled_training import train,CONFIRMATION_SEEDS
    with pytest.raises(ValueError,match='confirmation'):
        train(tmp_path/'run',steps=128,checkpoint_every=128,n_steps=128,seconds=.05,evaluation_seeds=[CONFIRMATION_SEEDS[0]])
    assert not (tmp_path/'run').exists()


def test_invalid_initial_actor_closes_allocated_environment(tmp_path,monkeypatch):
    from cartpole_sdk.learning.controlled_training import train,ControlledSwingEnv
    closed=[]
    original=ControlledSwingEnv.close
    def close(self):closed.append(self);original(self)
    monkeypatch.setattr(ControlledSwingEnv,'close',close)
    with pytest.raises(FileNotFoundError):
        train(tmp_path/'run',steps=128,checkpoint_every=128,n_steps=128,seconds=.05,init_actor=tmp_path/'missing.json')
    assert len(closed)==1


def test_full_rotation_task_constraint_terminates_real_spin_separately_from_fault(tmp_path):
    assert importlib.util.find_spec('cartpole_sdk.learning.constrained_swing'), 'constrained objective missing'
    from cartpole_sdk.learning.constrained_swing import ConstrainedSwingEnv
    experiment=make_experiment(tmp_path);experiment['simulation_config']['max_steps']=200
    class SpinningStart(ConstrainedSwingEnv):
        def initial_state(self,episode_seed,start):return (0.,0.,math.pi,30.)
    env=SpinningStart(experiment,[51],reward_scale=.01)
    try:
        env.reset()
        rewards=[]
        for _ in range(200):
            _,reward,terminated,truncated,info=env.step([0.]);rewards.append(reward)
            if terminated or truncated:break
        assert terminated and not truncated
        assert env.steps<200
        assert env.fault is None
        assert info['episode_result']['constraint_violation']=='full_rotation_excursion'
        assert not info['episode_result']['controlled_success']
        assert info['episode_result']['constraint_penalty']==600.
        assert reward < -5.
        assert sum(rewards)==pytest.approx(env.total_reward*.01)
        before=env.total_reward
        with pytest.raises(RuntimeError,match='reset'):env.step([0.])
        assert env.total_reward==before
    finally:env.close()


def test_crossing_wrapped_angle_boundary_does_not_trigger_rotation_constraint(tmp_path):
    from cartpole_sdk.learning.constrained_swing import ConstrainedSwingEnv
    experiment=make_experiment(tmp_path)
    class BoundaryStart(ConstrainedSwingEnv):
        def initial_state(self,episode_seed,start):return (0.,0.,math.pi-.001,1.)
    env=BoundaryStart(experiment,[51])
    try:
        env.reset()
        rewards=[]
        for _ in range(5):
            _,reward,terminated,truncated,info=env.step([0.]);rewards.append(reward)
        assert not terminated and truncated
        assert env.constraint_violation is None
        assert env.result()['unwrapped_range_rotations']<.1
        assert sum(rewards)==pytest.approx(env.total_reward)
    finally:env.close()
