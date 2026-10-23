import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def invoke(*args):
    return subprocess.run([sys.executable,'-m','cartpole_sdk.rig.operator',*args],capture_output=True,text=True)

def test_dry_run_resolves_operator_defaults_without_serial_or_privilege():
    result=invoke('--dry-run')
    assert result.returncode==0,result.stderr
    plan=json.loads(result.stdout)
    assert plan['console_args']==['--port','/dev/serial/by-id/usb-Teensyduino_USB_Serial_20242870-if00','--rate','250','--keep-board-params']
    assert plan['rt_priority']==10
    assert plan['affinity_args']==['--camera-service','cartpole-vision.service','--camera-cpus','0-3','--control-cpus','4-5']

def test_overrides_preserve_spaces_and_do_not_inject_conflicting_defaults():
    result=invoke('--dry-run','--port','/tmp/a device','--rate=100','--startup-profile','a profile.json','--rt-priority','0','--no-camera','--control-cpus','2-3')
    assert result.returncode==0,result.stderr
    p=json.loads(result.stdout)
    assert p['console_args']==['--port','/tmp/a device','--rate=100','--startup-profile','a profile.json']
    assert p['rt_priority']==0
    assert p['affinity_args']==['--no-camera','--control-cpus','2-3']

def test_operator_help_has_console_and_launcher_flags_without_opening_rig():
    result=invoke('--help')
    assert result.returncode==0,result.stderr
    for flag in ('--rt-priority','--dry-run','--keep-board-params','--port','--command'):
        assert flag in result.stdout

def test_bad_priority_rejected_before_launch():
    result=invoke('--dry-run','--rt-priority','100')
    assert result.returncode!=0
    assert 'priority' in result.stderr
