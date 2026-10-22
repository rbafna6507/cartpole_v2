import importlib.util
from pathlib import Path
import io,json,zipfile
import pytest
import torch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=HERE.parent/'combined-next'
BACKUP=ROOT/'runs/colab-filtered-joint-long-20261021-checkpoints'

def module():
    path=HERE/'resume.py'
    assert path.exists(), 'resume adapter must exist'
    spec=importlib.util.spec_from_file_location('resume_under_test',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def source():
    last=json.loads((BACKUP/'last-complete.json').read_text())
    ref=last['reports'][0]
    report=BACKUP/ref['local_path']
    cp=BACKUP/'runs/combined-long/ppo-seed11/checkpoints/step-000460800.zip'
    return report,ref['sha256'],cp

def equal(a,b):
    if isinstance(a,torch.Tensor): assert torch.equal(a,b)
    elif isinstance(a,dict):
        assert a.keys()==b.keys()
        for k in a: equal(a[k],b[k])
    elif isinstance(a,(tuple,list)):
        assert len(a)==len(b)
        for x,y in zip(a,b): equal(x,y)
    else: assert a==b

def test_full_optimizer_and_counters_survive_then_progress(tmp_path):
    m=module();report,h,cp=source();p=m.base.protocol(OLD/'protocol.json')
    torch.set_num_threads(1)
    env=m.base.TrainingEnv(p['experiment'],p['training_seeds'],reward_scale=.01)
    try:
        model,receipt=m.load_resume(report,h,cp,p,460800)
        model.set_env(env,force_reset=True)
        with zipfile.ZipFile(cp) as z:
            optimizer=torch.load(io.BytesIO(z.read('policy.optimizer.pth')),weights_only=True,map_location='cpu')
        equal(optimizer,model.policy.optimizer.state_dict())
        assert model.num_timesteps==460800
        before=m.base.model_weights_sha256(model);updates=model._n_updates
        model.learn(total_timesteps=1024,reset_num_timesteps=False)
        assert model.num_timesteps==461824
        assert model._n_updates>updates
        assert m.base.model_weights_sha256(model)!=before
        assert receipt['optimizer_restored'] and not receipt['bit_exact_resume']
    finally:env.close()

@pytest.mark.parametrize('bad',['report_hash','step','checkpoint_hash'])
def test_resume_rejects_wrong_lineage_before_training(tmp_path,bad):
    m=module();report,h,cp=source();p=m.base.protocol(OLD/'protocol.json');step=460800
    if bad=='report_hash':h='0'*64
    elif bad=='step':step=409600
    else:
        copied=tmp_path/cp.name;copied.write_bytes(cp.read_bytes()+b'broken');cp=copied
    with pytest.raises(ValueError):m.load_resume(report,h,cp,p,step)

def test_wrong_step_budget_rejected():
    m=module()
    with pytest.raises(ValueError):m.remaining_steps(460800,460800,51200)
    with pytest.raises(ValueError):m.remaining_steps(460801,1024000,51200)
    assert m.remaining_steps(460800,1024000,51200)==list(range(512000,1024001,51200))
