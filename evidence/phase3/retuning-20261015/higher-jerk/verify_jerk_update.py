from pathlib import Path
import json,time
root=Path('/home/rbafna/cartpole-v2-live/releases/platform-20261015-v5-jerk600')
port='/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00'
logroot=Path('/home/rbafna/cartpole-v2-runs/retune-20261015')/('jerk-stopped-verification-'+str(time.time_ns()));logroot.mkdir()
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
