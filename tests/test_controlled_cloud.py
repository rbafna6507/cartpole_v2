import importlib.util
import json
from pathlib import Path
import pytest


def module():
    assert importlib.util.find_spec('cartpole_sdk.learning.controlled_cloud'), 'controlled cloud module missing'
    from cartpole_sdk.learning import controlled_cloud
    return controlled_cloud


def test_prepare_freezes_foreground_objective_and_actor(tmp_path):
    m=module()
    repo=Path(__file__).resolve().parents[1]
    bundle=m.prepare(repo,tmp_path/'bundle',steps=2048,checkpoint_every=1024)
    assert bundle['recipe']['launch_mode']=='foreground real training cell'
    assert bundle['recipe']['objective']['id']=='controlled-swing-v3'
    assert bundle['recipe']['randomization']['encoder']
    text=(tmp_path/'bundle'/'remote.py').read_text()
    assert 'process.wait()' in text
    compile(text,'remote.py','exec')
    from cartpole_sdk.learning.colab_bundle import verify_bundle
    verify_bundle(tmp_path/'bundle')


def test_http_backup_verifies_checkpoint_and_rejects_wrong_recipe(tmp_path):
    assert importlib.util.find_spec('cartpole_sdk.learning.controlled_watch'), 'HTTP backup missing'
    from cartpole_sdk.learning.controlled_watch import poll
    from cartpole_sdk.learning.model_experiment import digest
    from hashlib import sha256
    import zipfile,io
    recipe=dict(run='runs/pilot',objective={'id':'controlled-swing-v2'})
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('weights','checkpoint')
    actor=b'{}'
    binding=dict(objective=recipe['objective'],experiment_sources_sha256={'controlled_training.py':'frozen'},provenance={'code_sha256':{}},seed=11,profile_content_sha256='profile',training_recipe={'initial_actor_content_sha256':'actor'})
    recipe['checkpoint_binding']=binding
    data=json.dumps(recipe).encode()
    manifest=dict(**binding,timesteps_completed=128,checkpoint_sha256=sha256(b.getvalue()).hexdigest(),actor_sha256=sha256(actor).hexdigest(),
                  )
    manifest['content_sha256']=digest(manifest)
    remote={'inputs/recipe.json':data,'job-status.json':json.dumps(dict(status='training',run='runs/pilot')).encode(),
            'runs/pilot/progress.json':json.dumps(dict(checkpoints=['checkpoints/step-000000128'])).encode(),
            'runs/pilot/checkpoints/step-000000128/manifest.json':json.dumps(manifest).encode(),
            'runs/pilot/checkpoints/step-000000128/checkpoint.zip':b.getvalue(),
            'runs/pilot/checkpoints/step-000000128/actor.json':actor}
    def fetch(name,path):path.write_bytes(remote[name])
    result=poll(fetch,tmp_path/'backups',recipe_bytes=data,source_hashes={'src/cartpole_sdk/learning/controlled_training.py':'frozen'})
    assert result['verified_checkpoints']==1
    assert (tmp_path/'backups'/'checkpoints'/'step-000000128'/'checkpoint.zip').exists()
    for field,value in (('seed',23),('profile_content_sha256','wrong'),('experiment_sources_sha256',{}),('training_recipe',{'initial_actor_content_sha256':'wrong'})):
        bad=dict(manifest);bad[field]=value;bad.pop('content_sha256');bad['content_sha256']=digest(bad)
        remote['runs/pilot/checkpoints/step-000000128/manifest.json']=json.dumps(bad).encode()
        with pytest.raises(ValueError,match='binding'):poll(fetch,tmp_path/'backups',recipe_bytes=data,source_hashes={'src/cartpole_sdk/learning/controlled_training.py':'frozen'})
    remote['inputs/recipe.json']=b'{}'
    with pytest.raises(ValueError,match='recipe'):poll(fetch,tmp_path/'backups',recipe_bytes=data,source_hashes={'src/cartpole_sdk/learning/controlled_training.py':'frozen'})


def test_failed_job_without_progress_is_reported_immediately(tmp_path):
    from cartpole_sdk.learning.controlled_watch import poll
    recipe=json.dumps(dict(run='runs/pilot')).encode()
    remote={'inputs/recipe.json':recipe,'job-status.json':json.dumps(dict(status='failed',run='runs/pilot',error='trainer setup failed')).encode()}
    def fetch(name,path):
        if name not in remote:raise FileNotFoundError(name)
        path.write_bytes(remote[name])
    result=poll(fetch,tmp_path/'backup',recipe_bytes=recipe,source_hashes={})
    assert result['status']=='failed'
    assert result['error']=='trainer setup failed'
