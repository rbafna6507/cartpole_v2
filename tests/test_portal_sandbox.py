"""Bounded real pipe IPC, process cleanup and Linux adversarial isolation."""
from dataclasses import asdict
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from cartpole_sdk.contracts import Session, Observation
from cartpole_sdk.portal.sandbox import PolicyChannel, Sandbox, SandboxError

OBS=Observation('s','clock',1,0,'test',())

class IPCTests(unittest.TestCase):
    def child(self,response,*,max_acceleration=.25):
        code='import sys,json,time\nfor line in sys.stdin:\n r=json.loads(line)\n if r["type"]=="reset": print(json.dumps({"type":"reset_ack","nonce":r["nonce"]}),flush=True)\n else:\n  '+response+'\n'
        process=subprocess.Popen([sys.executable,'-I','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        return PolicyChannel(process,action_timeout=.04,max_acceleration=max_acceleration)
    def test_reset_then_numeric_action_uses_actual_sdk_objects(self):
        with self.child('print(json.dumps({"type":"action","sequence":r["sequence"],"acceleration":0.1}),flush=True)') as channel:
            channel.reset(Session('s','clock'))
            self.assertEqual(channel.act(OBS),.1)
    def test_invalid_nonfinite_bool_wrong_sequence_and_oversize_rejected(self):
        for response in ('print("not-json",flush=True)','print(json.dumps({"type":"action","sequence":r["sequence"],"acceleration":True}),flush=True)','print(json.dumps({"type":"action","sequence":99,"acceleration":0}),flush=True)','print("x"*5000,flush=True)','print(json.dumps({"type":"action","sequence":r["sequence"],"acceleration":float("nan")}),flush=True)'):
            with self.subTest(response=response),self.child(response) as channel:
                channel.reset(Session('s','clock'))
                with self.assertRaises(SandboxError):channel.act(OBS)
    def test_trusted_channel_ceiling_accepts_range_and_rejects_excess(self):
        for value,accepted in ((1.,True),(25.,True),(25.01,False)):
            response='print(json.dumps({"type":"action","sequence":r["sequence"],"acceleration":'+repr(value)+'}),flush=True)'
            with self.subTest(value=value),self.child(response,max_acceleration=25.) as channel:
                channel.reset(Session('s','clock'))
                if accepted:self.assertEqual(channel.act(OBS),value)
                else:
                    with self.assertRaises(SandboxError):channel.act(OBS)

    def test_policy_output_cannot_override_trusted_channel_ceiling(self):
        response='print(json.dumps({"type":"action","sequence":r["sequence"],"acceleration":1,"max_acceleration":25}),flush=True)'
        with self.child(response) as channel:
            channel.reset(Session('s','clock'))
            with self.assertRaises(SandboxError):channel.act(OBS)

    def test_timeout_and_cleanup_terminate_real_process(self):
        with self.child('time.sleep(10)') as channel:
            channel.reset(Session('s','clock'));process=channel.process
            began=time.monotonic()
            with self.assertRaises(SandboxError):channel.act(OBS)
            self.assertLess(time.monotonic()-began,.5)
        self.assertIsNotNone(process.poll())
    def test_idle_child_wall_deadline_is_independently_enforced(self):
        code='import time; time.sleep(10)'
        process=subprocess.Popen([sys.executable,'-I','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        with PolicyChannel(process,wall_seconds=.04,startup_timeout=.01) as channel:
            deadline=time.monotonic()+.5
            while process.poll() is None and time.monotonic()<deadline:time.sleep(.005)
            self.assertIsNotNone(process.poll())

    def test_stderr_diagnostic_is_bounded_and_separate_from_actions(self):
        with self.child('print("diagnostic"*500,file=sys.stderr,flush=True); print(json.dumps({"type":"action","sequence":r["sequence"],"acceleration":0}),flush=True)') as channel:
            channel.reset(Session('s','clock'));self.assertEqual(channel.act(OBS),0)
            deadline=time.monotonic()+.1
            while not channel.stderr_tail and time.monotonic()<deadline:time.sleep(.001)
            self.assertIn('diagnostic',channel.stderr_tail)
            self.assertLessEqual(len(channel.stderr_tail.encode()),4096)

    def test_output_flood_bounded_and_child_reaped(self):
        with self.child('print("x"*100000,flush=True)') as channel:
            channel.reset(Session('s','clock'))
            with self.assertRaises(SandboxError):channel.act(OBS)
            self.assertLessEqual(channel.buffered_bytes,16384)
    @unittest.skipIf(sys.platform=='linux' and shutil.which('bwrap'),'tests absent-runtime fail-closed path')
    def test_missing_runtime_fails_before_policy_import(self):
        with tempfile.TemporaryDirectory() as root:
            sentinel=Path(root)/'imported';source=Path(root)/'source.py'
            source.write_text(f'open({str(sentinel)!r},"w").write("bad")\n')
            with self.assertRaises(SandboxError):Sandbox(source).launch()
            self.assertFalse(sentinel.exists())

@unittest.skipUnless(sys.platform=='linux' and shutil.which('bwrap'),'Linux bwrap sandbox required')
class LinuxSandboxTests(unittest.TestCase):
    def run_policy(self,body,*,sdk_root=None):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.py'
            source.write_text('import socket\nfrom cartpole_sdk.contracts import Acceleration\nclass Policy:\n def reset(self,session): pass\n def act(self,observation):\n'+''.join('  '+line+'\n' for line in body.splitlines())+'\ndef create_policy(): return Policy()\n')
            with Sandbox(source,action_timeout=.25,sdk_root=sdk_root).launch() as channel:
                channel.reset(Session('s','clock'));return channel.act(OBS)
    def test_valid_policy_runs_inside_actual_sandbox(self):self.assertEqual(self.run_policy('return Acceleration(0.1)'),.1)
    def test_file_hosthome_serial_network_fork_exec_are_denied(self):
        attempts=[('open("/tmp/write","w")',(13,30)),('open("/dev/shm/write","w")',(2,)),('open("/home/private-secret","rb")',(2,)),('open("/usr/host-write","w")',(13,30)),('open("/dev/ttyACM0","rb")',(2,)),('socket.socket()',(1,)),('__import__("os").fork()',(1,)),('__import__("os").execl("/usr/bin/true","true")',(1,))]
        for attempt,expected_errno in attempts:
            body='try:\n '+attempt+'\nexcept OSError as exc:\n return Acceleration(0.1 if exc.errno in '+repr(expected_errno)+' else 0)\nreturn Acceleration(0)'
            with self.subTest(attempt=attempt,expected_errno=expected_errno):self.assertEqual(self.run_policy(body),.1)
    def test_sdk_mount_excludes_unrelated_site_package_files(self):
        import cartpole_sdk
        with tempfile.TemporaryDirectory() as root:
            sdk_root=Path(root)/'site-packages';sdk_root.mkdir()
            shutil.copytree(Path(cartpole_sdk.__file__).parent,sdk_root/'cartpole_sdk')
            (sdk_root/'unrelated-secret').write_text('synthetic sentinel')
            body='try:\n open("/sdk/unrelated-secret","rb")\nexcept FileNotFoundError:\n return Acceleration(0.1)\nreturn Acceleration(0)'
            self.assertEqual(self.run_policy(body,sdk_root=sdk_root),.1)

    def test_cpu_memory_and_output_abuse_fail_bounded(self):
        for body in ('while True: pass','x=bytearray(2**31)\nreturn Acceleration(0)','print("x"*100000)\nreturn Acceleration(0)'):
            with self.subTest(body=body),self.assertRaises(SandboxError):self.run_policy(body)
