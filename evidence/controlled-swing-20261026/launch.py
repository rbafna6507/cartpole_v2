"""Launch exactly one reviewed CPU campaign; no automatic retries."""
import json,os,pathlib,subprocess,sys,time,uuid
from hashlib import sha256
from cartpole_sdk.learning.colab_bundle import verify_bundle
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
BUNDLE=HERE/'colab-v3-1024000-bound'
SESSION='cartpole-controlled-v3-20261026'
STATE=pathlib.Path.home()/'.config/colab-cli/sessions.json'
CLI=ROOT/'runs/colab-cli-venv/bin/colab'
LOCAL=ROOT/'runs/controlled-v3-20261026-cloud'
BASE=[str(CLI),'--auth','oauth2','--config',str(STATE)]

def record(value):
    temp=HERE/'launch.tmp';temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(HERE/'launch.json')

def call(args,log,timeout=600):
    with (LOCAL/log).open('xb') as stream:
        subprocess.run(BASE+args,check=True,timeout=timeout,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT)


def main():
    verify_bundle(BUNDLE)
    if (HERE/'launch.json').exists():raise FileExistsError('launch receipt already exists; inspect, never retry automatically')
    if STATE.exists() and SESSION in json.loads(STATE.read_text()):raise ValueError('session already registered')
    reservation=STATE.parent/('.cartpole-launch-'+sha256(SESSION.encode()).hexdigest()+'.json')
    with reservation.open('x') as stream:json.dump(dict(session=SESSION,bundle=str(BUNDLE)),stream)
    LOCAL.mkdir(parents=True,exist_ok=False)
    receipt=dict(session=SESSION,bundle=str(BUNDLE),bundle_sha256=sha256((BUNDLE/'bundle.json').read_bytes()).hexdigest(),stage='reserved',started_unix=time.time(),hardware='CPU',budget=1024000,checkpoint_every=25600)
    record(receipt)
    call(['new','-s',SESSION],'allocate.log')
    if SESSION not in json.loads(STATE.read_text()):raise ValueError('allocation did not register session')
    receipt['stage']='allocated';record(receipt);print('allocated',flush=True)
    for local,remote in (('source.zip','source.zip'),('inputs.zip','inputs.zip'),('remote.py','cartpole-launch.py')):
        call(['upload','-s',SESSION,str(BUNDLE/local),'/content/'+remote],local+'.log')
    nonce=uuid.uuid4().hex
    receipt.update(stage='setup_running',setup_nonce=nonce);record(receipt)
    call(['exec','-s',SESSION,'--timeout','1800','-f',str(BUNDLE/'remote.py'),'--env','CARTPOLE_ACTION=setup','--env','CARTPOLE_NONCE='+nonce],'setup.log',1890)
    expected='CARTPOLE_REMOTE_OK '+json.dumps(dict(action='setup',nonce=nonce))
    if expected not in (LOCAL/'setup.log').read_text().splitlines():raise ValueError('setup has no matching success receipt')
    receipt.update(stage='setup_verified',setup_verified_unix=time.time());record(receipt);print('setup verified',flush=True)
    preflight_nonce=uuid.uuid4().hex
    preflight=LOCAL/'preflight.py'
    preflight.write_text('import json,pathlib,subprocess\nroot=pathlib.Path("/content/cartpole-training")\ncode="from cartpole_sdk.learning.ppo import provenance;import json;print(json.dumps(provenance()))"\nresult=subprocess.run([str(root/".venv/bin/python"),"-c",code],cwd=root,capture_output=True,text=True,check=True)\nactual=json.loads(result.stdout)\nexpected=json.loads((root/"inputs/recipe.json").read_text())["checkpoint_binding"]["provenance"]\nprint(json.dumps(dict(actual=actual,expected_dependencies=expected["dependencies"])))\nif actual!=expected:raise ValueError("cloud dependency/source provenance differs from frozen checkpoint binding")\nprint("CARTPOLE_PREFLIGHT_OK '+preflight_nonce+'")\n')
    call(['exec','-s',SESSION,'--timeout','120','-f',str(preflight)],'preflight.log',210)
    if 'CARTPOLE_PREFLIGHT_OK '+preflight_nonce not in (LOCAL/'preflight.log').read_text().splitlines():raise ValueError('cloud provenance preflight failed; training not launched')
    receipt.update(stage='preflight_verified',preflight_nonce=preflight_nonce);record(receipt)
    foreground_nonce=uuid.uuid4().hex
    command=BASE+['exec','-s',SESSION,'--timeout','86400','-f',str(BUNDLE/'remote.py'),'--env','CARTPOLE_ACTION=run','--env','CARTPOLE_NONCE='+foreground_nonce]
    (LOCAL/'foreground-command.json').write_text(json.dumps(dict(command=command,nonce=foreground_nonce),indent=2)+'\n')
    old_runner=ROOT/'runs/colab-filtered-joint-recovery-20261021/foreground_runner.py'
    (LOCAL/'foreground_runner.py').write_bytes(old_runner.read_bytes())
    with (LOCAL/'foreground-client.log').open('xb') as stream:
        process=subprocess.Popen(['/usr/bin/caffeinate','-i',str(ROOT/'.venv/bin/python'),str(LOCAL/'foreground_runner.py')],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    receipt.update(stage='foreground_dispatched',client_pid=process.pid,foreground_nonce=foreground_nonce,foreground_command=command);record(receipt)
    watch=ROOT/'runs/controlled-v3-20261026-backups'
    watch_command=['/usr/bin/caffeinate','-i',str(ROOT/'.venv/bin/python'),'-m','cartpole_sdk.learning.controlled_watch',str(BUNDLE),'--session',SESSION,'--output',str(watch),'--cli',str(CLI),'--cli-pins',str(ROOT/'evidence/policy-recovery-20261021/combined-next/http-checkpoint-cli-pins.json'),'--interval','30','--max-seconds','28800']
    with (LOCAL/'watch.log').open('xb') as stream:
        watcher=subprocess.Popen(watch_command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    receipt.update(stage='foreground_and_watcher_dispatched',watcher_pid=watcher.pid,watcher_output=str(watch),watcher_command=watch_command);record(receipt)
    print(json.dumps(dict(session=SESSION,stage=receipt['stage'],watcher_output=str(watch))),flush=True)

if __name__=='__main__':main()
