"""Operator deployment; run only after the owner confirms motor supply OFF."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
import serial
p=argparse.ArgumentParser();p.add_argument('--motor-power-off-confirmed',action='store_true',required=True);p.parse_args()
root=Path('/home/rbafna/cartpole-v2-live/releases/platform-20261015-v5-jerk600')
hexfile=root/'artifacts/executor-v5-calmodel-jerk600.hex'
assert hashlib.sha256(hexfile.read_bytes()).hexdigest()=='baf8b176fcb026c9d76cdc8a75f27698845f4e34a98e3733810c4103765f6e26'
port='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
owner=subprocess.run(['fuser',port],capture_output=True,text=True)
assert owner.returncode==1 and not owner.stdout.strip(),f'Serial ownership uncertain: {owner}'
loader=Path('/home/rbafna/cartpole-v2-live/tools/loader-2.3/teensy_loader_cli');assert os.access(loader,os.X_OK)
logroot=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')/('jerk-update-'+str(time.time_ns()));logroot.mkdir()
print(json.dumps({'phase':'upload','log':str(logroot)}),flush=True)
with (logroot/'upload.log').open('w') as stream:
 proc=subprocess.Popen([str(loader),'--mcu=TEENSY41','-w','-v',str(hexfile)],stdout=stream,stderr=subprocess.STDOUT)
 try:
  # Trusted Teensy USB core reboot request; never perform with motor supply on.
  try:
   with serial.Serial(port,134,timeout=1):time.sleep(.25)
  except (serial.SerialException,OSError) as exc:
   time.sleep(.5)
   if Path(port).exists():raise
   print(json.dumps({'phase':'USB disconnected during bootloader request','detail':str(exc)}),flush=True)
  code=proc.wait(timeout=100)
 except BaseException:
  proc.terminate();proc.wait(timeout=5);raise
assert code==0,(logroot/'upload.log').read_text()
print((logroot/'upload.log').read_text(),flush=True)
deadline=time.monotonic()+20
while not Path(port).exists():
 assert time.monotonic()<deadline,'Serial did not return after upload'
 time.sleep(.2)
time.sleep(1)
from dataclasses import asdict
from cartpole_sdk.rig import Rig
from cartpole_sdk.control import ControllerParameters
import math
with Rig(port,rate_hz=250,log_dir=logroot) as r:
 r.stop();info=r.get_info();state=r.state
 assert info.firmware=='executor-v5-calmodel' and info.encoder_upright_raw==351 and info.reference_saved
 assert info.encoder_conf_valid and info.encoder_conf==768
 assert state.healthy and state.switch_profile and not state.enabled and not state.fault and not state.homed
 assert state.misses==0
 defaults=r.get_parameters()
 for key,value in asdict(ControllerParameters()).items():
  assert math.isclose(defaults[key],value,rel_tol=2e-6,abs_tol=2e-7),(key,defaults[key],value)
 roundtrip=[]
 for value in (300,600,150):
  actual=r.set_parameter('jmax',value);assert actual==value;roundtrip.append(actual)
 loaded=r.load_parameters(root/'artifacts/pre-jerk-parameters.json')
 assert loaded['jmax']==150 and loaded['bal_pw']==4.5
 final_parameters=r.get_parameters();r.stop();final_info=r.get_info();final=r.state
 assert final_info.encoder_upright_raw==351 and final_info.reference_saved and final_info.encoder_conf_valid
 assert final.healthy and final.switch_profile and not final.enabled and not final.fault and not final.homed and final.misses==0
 result={'path':str(logroot),'info':asdict(info),'boot_parameters':defaults,'stopped_jerk_roundtrip':roundtrip,'restored_profile':final_parameters,'final':asdict(final),'final_info':asdict(final_info),'motor_supply':'owner confirmed OFF before invocation','motion_commands_sent':False,'home_required_after_power_on':True}
 (logroot/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2),flush=True)
