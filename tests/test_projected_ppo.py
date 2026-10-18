import importlib.util
import numpy as np
import pytest
pytest.importorskip('stable_baselines3')
from test_ppo_training import make_experiment


def test_projection_removes_equilibrium_bias_without_other_changes(tmp_path):
    assert importlib.util.find_spec('cartpole_sdk.learning.projected_ppo'), 'equilibrium-constrained PPO missing'
    import torch
    from cartpole_sdk.learning.projected_ppo import EquilibriumPPO, equilibrium_observation
    from cartpole_sdk.learning.diagnostics import DiagnosticEnv
    env=DiagnosticEnv(make_experiment(tmp_path),(11,),variant='upright')
    try:
        m=EquilibriumPPO('MultiInputPolicy',env,seed=3,n_steps=8,batch_size=4,n_epochs=1)
        with torch.no_grad():m.policy.action_net.bias.add_(.3)
        obs=equilibrium_observation()
        initial=m.predict(obs,deterministic=True)[0][0]
        assert abs(initial)>.2
        before={k:v.clone() for k,v in m.policy.state_dict().items()}
        m.project_equilibrium()
        assert abs(m.predict(obs,deterministic=True)[0][0])<1e-7
        assert all(torch.equal(v,before[k]) for k,v in m.policy.state_dict().items() if k!='action_net.bias')
        m.learn(8)
        assert m.num_timesteps==8
        assert abs(m.predict(obs,deterministic=True)[0][0])<1e-7
        # The saved result is still a standard actor, no wrapper/fallback required.
        m.save(tmp_path/'model.zip')
        from stable_baselines3 import PPO
        loaded=PPO.load(tmp_path/'model.zip',device='cpu')
        np.testing.assert_allclose(loaded.predict(obs,deterministic=True)[0],m.predict(obs,deterministic=True)[0],atol=1e-7)
    finally:env.close()
