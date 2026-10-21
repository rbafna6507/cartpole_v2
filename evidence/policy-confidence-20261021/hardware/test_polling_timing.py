import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys,threading,unittest
from unittest.mock import patch
HERE=Path(__file__).parent;sys.path.insert(0,str(HERE))
import polling_timing_instrumentation as poll
from timing_instrumentation import TimingRecorder
from cartpole_sdk.rig.client import RigError
import cartpole_sdk.rig.client as client

class PollingTests(unittest.TestCase):
 def rig(self):
  r=poll.PollingRig('/unused',timings=TimingRecorder());r._connected=True;r._state=SimpleNamespace(tick=10,unwrapped_tick=10);return r
 def test_false_and_spurious_wakes_keep_original_deadline(self):
  r=self.rig();clock=[0.];waits=[]
  def wait(condition,timeout):
   waits.append(timeout);clock[0]+=timeout;return len(waits)%2==0
  with patch.object(client.time,'monotonic',side_effect=lambda:clock[0]),patch.object(threading.Condition,'wait',autospec=True,side_effect=wait):
   with self.assertRaises(TimeoutError):r.wait_state(after_tick=10,timeout=.005)
  self.assertGreaterEqual(len(waits),5);self.assertTrue(all(0<x<=.001 for x in waits));self.assertAlmostEqual(sum(waits),.005)
  self.assertFalse(r._condition.polling_active());self.assertEqual(r._sequence,0)
 def test_new_state_after_false_return_satisfies_predicate(self):
  r=self.rig();clock=[0.];calls=[]
  def wait(condition,timeout):
   calls.append(timeout);clock[0]+=timeout
   if len(calls)==3:r._state=SimpleNamespace(tick=11,unwrapped_tick=11)
   return len(calls)==2
  with patch.object(client.time,'monotonic',side_effect=lambda:clock[0]),patch.object(threading.Condition,'wait',autospec=True,side_effect=wait):
   result=r.wait_state(after_tick=10,timeout=.1)
  self.assertEqual(result.tick,11);self.assertEqual(len(calls),3);self.assertEqual(r._sequence,0)
 def test_cap_is_inactive_outside_public_control_wait(self):
  r=self.rig()
  with patch.object(threading.Condition,'wait',autospec=True,return_value=False) as wait:
   with r._condition:r._condition.wait(.08)
  self.assertEqual(wait.call_args.args[1],.08);self.assertEqual(r._condition.polling_summary()['calls'],0)
 def test_fault_propagates_and_poll_scope_restores(self):
  r=self.rig();clock=[0.]
  def wait(condition,timeout):clock[0]+=timeout;r.error=RigError('fault1');return False
  with patch.object(client.time,'monotonic',side_effect=lambda:clock[0]),patch.object(threading.Condition,'wait',autospec=True,side_effect=wait):
   with self.assertRaisesRegex(RigError,'fault1'):r.wait_state(after_tick=10,timeout=.1)
  self.assertFalse(r._condition.polling_active())
 def test_shorter_remaining_deadline_is_not_extended(self):
  r=self.rig();clock=[0.];waits=[]
  def wait(condition,timeout):waits.append(timeout);clock[0]+=timeout;return False
  with patch.object(client.time,'monotonic',side_effect=lambda:clock[0]),patch.object(threading.Condition,'wait',autospec=True,side_effect=wait):
   with self.assertRaises(TimeoutError):r.wait_state(after_tick=10,timeout=.0004)
  self.assertEqual(waits,[.0004])
 def test_driver_retains_lease_and_duration_limit(self):
  spec=importlib.util.spec_from_file_location('zero_poll_v3',HERE/'zero-timing-poll-v3.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertEqual(m.LEASE_MS,20);self.assertEqual(m.parse_args(['--out','/unused','--duration','60']).duration,60)
  self.assertIs(m.InstrumentedRig,poll.PollingRig)

if __name__=='__main__':unittest.main()
