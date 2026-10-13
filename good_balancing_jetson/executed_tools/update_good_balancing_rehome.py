import hashlib,json,shutil,tarfile,subprocess
from pathlib import Path
home=Path.home();dst=home/'good_balancing_jetson';local=dst/'local_repository_snapshot';active=home/'cartpole_inverted_pendulum'
assert (dst/'manifest.json').exists()
meta=json.loads(Path('/tmp/good_balancing_rehome_update.json').read_text());tar=Path('/tmp/good_balancing_rehome_update.tar.gz');assert hashlib.sha256(tar.read_bytes()).hexdigest()==meta['sha256']
with tarfile.open(tar) as t:t.extractall(local)
with tarfile.open(tar) as t:
 for m in t:
  if m.isfile():assert hashlib.sha256((local/m.name).read_bytes()).digest()==hashlib.sha256(t.extractfile(m).read()).digest()
shutil.copy2(local/'presets/teensy_jetson_20261012.json',dst/'settings.json')
shutil.copy2(local/'experiments/20261012_balance_tuning/rehome_02/result.json',dst/'rehome_verification.json')
# Retain both actual pre-update console files before updating the active installation.
backup=dst/'before_rehome_console';backup.mkdir()
shutil.copy2(active/'cartpole.py',backup/'root_cartpole.py')
shutil.copy2(active/'teensy_working_jetson_compatible/cartpole.py',backup/'bundle_cartpole.py')
for p in [active/'cartpole.py',active/'teensy_working_jetson_compatible/cartpole.py']:
 shutil.copy2(local/'cartpole.py',p)
 assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256((local/'cartpole.py').read_bytes()).digest()
(dst/'run_console.sh').write_text('''#!/bin/sh
cd /home/rbafna/good_balancing_jetson/local_repository_snapshot || exit 1
exec /home/rbafna/cartpole_inverted_pendulum/.venv/bin/python cartpole.py --text --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00 "$@"
''');(dst/'run_console.sh').chmod(0o755)
with (dst/'README.txt').open('a') as f:f.write('''
REHOME UPDATE
Launch the saved console with ~/good_balancing_jetson/run_console.sh
At >>>, type rehome while stopped and hanging still. If in the dashboard,
q + Enter returns to >>>. Any key cancels rehome. It returns at <=40mm/s to
within1mm of existing home and disables drivers; it never resets home/upright.
It cannot recover from missed steps: physically recenter and set home if needed.
The active original Jetson console also has this command. The original files
remain in before_rehome_console and jetson_repository_snapshot.
64 host tests passed. Live rehome returned +6.79mm to +.94mm and reported idle,
zero velocity. rehome_verification.json records this latest stopped state;
final_state.json is the earlier snapshot after auto_23 and recenter_24.
First harness checked before STOP acknowledgment, was refused, and was corrected;
all recordings retained. Balancing settings and Teensy firmware unchanged.
User subsequently confirmed deliberately pushing the pendulum when it last fell;
this is a disturbed trial, with event timing not logged.
''')
manifest=json.loads((dst/'manifest.json').read_text());manifest['rehome_update']=meta;manifest['active_console_updated']=True;(dst/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for name in ['create_good_balancing_archive.py','update_good_balancing_rehome.py','test_rehome_jetson.py','test_rehome_retry.py']:
 shutil.copy2('/tmp/'+name,dst/'executed_tools'/name)
lines=[]
for p in sorted(dst.rglob('*')):
 if p.is_file() and not p.is_symlink() and p.name!='SHA256SUMS':
  h=hashlib.sha256()
  with p.open('rb') as f:
   for block in iter(lambda:f.read(1048576),b''):h.update(block)
  lines.append(h.hexdigest()+'  '+str(p.relative_to(dst)))
(dst/'SHA256SUMS').write_text('\n'.join(lines)+'\n')
subprocess.run([str(dst/'run_console.sh'),'--help'],check=True,stdout=subprocess.DEVNULL)
print(json.dumps({'archive':str(dst),'files_hashed':len(lines),'rehome_verified':True,'active_console_updated':True,'launcher_help_ok':True}))
