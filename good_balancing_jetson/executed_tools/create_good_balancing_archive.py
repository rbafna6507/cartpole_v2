import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
home=Path.home(); dst=home/'good_balancing_jetson'; src=home/'cartpole_inverted_pendulum'
manifest=json.loads(Path('/tmp/good_balancing_manifest.json').read_text())
tar=Path('/tmp/good_balancing_jetson_local.tar.gz')
assert hashlib.sha256(tar.read_bytes()).hexdigest()==manifest['local_archive_sha256']
dst.mkdir(exist_ok=False)
excluded=set(manifest['excluded_components'])
shutil.copytree(src,dst/'jetson_repository_snapshot',symlinks=True,ignore=lambda directory,names:[n for n in names if n in excluded or n.endswith('.pyc')])
with tarfile.open(tar) as t:t.extractall(dst)
(dst/'executed_tools').mkdir()
for name in ('cartpole_auto_trial.py','cartpole_recenter.py'):shutil.copy2('/tmp/'+name,dst/'executed_tools'/name)
local=dst/'local_repository_snapshot'; exp=local/'experiments/20261012_balance_tuning'
for source,target in [(exp/'final_snapshot_23/snapshot.json','final_state.json'),(exp/'trial_comparison.json','trial_summary.json'),(local/'presets/teensy_jetson_20261012.json','settings.json'),(local/'presets/teensy_jetson_20261012.txt','restore_parameters.txt')]:shutil.copy2(source,dst/target)
manifest['remote_commit']=subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()
manifest['remote_status']=subprocess.check_output(['git','-C',str(src),'status','--short'],text=True)
manifest['firmware_flashed_during_tuning']=False
manifest['note']='Working-tree snapshots, including uncommitted changes. Dependency environments, Git internals and caches excluded. Existing source_baseline and baseline_build retained.'
(dst/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(dst/'README.txt').write_text('''GOOD BALANCING JETSON - October 12, 2026 tuning snapshot

Firmware: swingup-125mm-60t-v33-teensy41. No firmware change or flash during tuning.
Current AUTO settings: pw=4.5, pz=.85, pc1=-3, pc2=-4, leff=.124, bw=30.
Rail half-length .26m; runtime speed ceiling 1.5m/s; approach/catch .3m/s.
Full runtime readback, encoder and stopped state: final_state.json.

Results: auto_20 and auto_21 held continuously over42s each. auto_22 lost
balance; user reported possible deliberate interference, without timestamps.
auto_23 repeated identical settings for45s, lost once, recaptured, and finished
balanced (balance bouts16.683s and24.905s). These are working settings, not proof
of uninterrupted repeatability. All failures are preserved in the data.
Cart returned near home after auto_23, x=-.00094m, drivers disabled.
Position is inferred from motor steps, not an independent physical measurement.

CONTENTS
local_repository_snapshot: current Mac source tree, cleanup, analysis, presets,
  passive measurement scripts, experiments and pre-cleanup source/build backups.
jetson_repository_snapshot: original Jetson tree and all its recordings.
executed_tools: exact live trial and recenter scripts used from /tmp.
settings.json / restore_parameters.txt: AUTO settings and console commands.
trial_summary.json: aggregate measured trial metrics.
manifest.json: source commits, uncommitted status, exclusions and transfer hash.
SHA256SUMS: per-file integrity checks for this saved directory.

RUN THE SAVED CONSOLE (does not start motion)
cd ~/good_balancing_jetson/local_repository_snapshot
~/cartpole_inverted_pendulum/.venv/bin/python cartpole.py --text --port /dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00

Then paste restore_parameters.txt commands into that console. These stop drivers,
restore runtime AUTO settings and request a readback; they do not home, calibrate,
or start AUTO. Inspect params before starting a supervised run. Runtime set
parameters are lost on board reset; encoder upright reference is saved in EEPROM.
The current upright reference is1411 (physical capture1425 minus14-count trim).
Do not blindly apply that raw reference after moving the arm, magnet or sensor.
Only issue home with the cart physically centered. STOP disables all drivers.
The upright-only bal mode is separate and was not validated with this preset.

DEPENDENCIES
Python virtualenvs are excluded; command above reuses the existing Jetson venv.
For an independent console environment, create a Python3 venv and install
pyserial. Numpy/scipy are needed for analysis; matplotlib for graphical plotting.
Git internals, dependency environments, caches and build/build_teensy directories
are excluded; specifically named baseline_build/source_baseline are included.
No repository commits, pushes or firmware uploads are performed by this archive.
''')
# Verify extracted source against the transfer archive, including symbolic links.
checked=0
with tarfile.open(tar) as t:
 for member in t:
  path=dst/member.name
  if member.isfile():
   assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(t.extractfile(member).read()).digest(),str(path)
   checked+=1
  elif member.issym():assert path.is_symlink() and str(path.readlink())==member.linkname
snapshot=json.loads((dst/'final_state.json').read_text()); assert snapshot['parameters']['rail']==.26
lines=[]
for p in sorted(dst.rglob('*')):
 if p.is_file() and not p.is_symlink():lines.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(dst)))
(dst/'SHA256SUMS').write_text('\n'.join(lines)+'\n')
print(json.dumps({'archive':str(dst),'local_files_verified':checked,'files_hashed':len(lines),'bytes':sum(p.stat().st_size for p in dst.rglob('*') if p.is_file() and not p.is_symlink())}))
