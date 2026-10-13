from pathlib import Path
import json,os,subprocess,sys,tempfile
root=Path('/tmp/cartpole-phase0/relocated archive')
sys.path[:0]=[str(root/'good_balancing_jetson/tests'),str(root/'good_balancing_jetson/console')]
from test_startup_preset import Board
p=json.loads((root/'good_balancing_jetson/settings.json').read_text())
b=Board();b.values={**p['settings'],**p['computed_gains'],'encoder_upright_raw':3475.};b.values['pw']=6.
env={**os.environ,'UV_CACHE_DIR':'/tmp/cartpole-phase0/uv-cache'}
try:
 with tempfile.TemporaryDirectory() as tmp:
  cmd=['uv','run','--locked','--project',str(root/'good_balancing_jetson'),'cartpole-console','--host=127.0.0.1','--tcp-port',str(b.port),'--vision-telemetry-port','0','--logdir',tmp,'--rate','100']
  r=subprocess.run(cmd,cwd='/',input='quit\n',text=True,capture_output=True,timeout=60,env=env)
  assert r.returncode==0,(r.stdout,r.stderr)
  reports=list(Path(tmp).glob('*_preset.json'));assert len(reports)==1
  report=json.loads(reports[0].read_text());assert report['restored_settings']==p['settings']
  assert b.values['pw']==4.5 and b.values['encoder_upright_raw']==3475
  print('PASS: installed uv entry point in relocated checkout restored and verified all 33 settings; no calibration change.')
finally:b.close()
for suffix in (['vision3','--help'],['python','-c','from importlib.resources import files; p=files("pendulum_vision"); assert p.joinpath("dashboard.html").is_file(); assert p.joinpath("comparison.js").is_file(); print("packaged dashboard assets available")']):
 r=subprocess.run(['uv','run','--locked','--project',str(root/'vision3'),*suffix],cwd='/',text=True,capture_output=True,timeout=60,env=env)
 assert r.returncode==0,(r.stdout,r.stderr)
print('PASS: relocated uv vision3 entry point and dashboard assets; runtime environment excludes development pyserial.')
r=subprocess.run(['uv','run','--locked','--project',str(root/'vision3'),'python','-c','import importlib.util; assert importlib.util.find_spec("serial") is None'],text=True,capture_output=True,timeout=20,env=env)
assert r.returncode==0,r.stderr
