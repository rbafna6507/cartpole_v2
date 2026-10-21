import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import threading
import tempfile
from collections import deque
from dataclasses import make_dataclass
import unittest
from unittest.mock import patch
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
import timing_instrumentation as ti
from cartpole_sdk.rig.client import Rig
from cartpole_sdk.learning.balance_hardware import BalanceOnlyPolicy

def load(name):
 spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class TimingTests(unittest.TestCase):
 def test_recorder_is_bounded_and_contains_cpu_wall(self):
  r=ti.TimingRecorder(capacity=1);r.measure('one',lambda:42);r.measure('two',lambda:43)
  s=r.snapshot();self.assertEqual(s['dropped_events'],1);events=s['threads'][0]['events'];self.assertEqual(len(events),1)
  self.assertGreaterEqual(events[0][2],events[0][1]);self.assertGreaterEqual(events[0][3],0)
 def test_actor_wrapper_preserves_result_errors_and_restores(self):
  r=ti.TimingRecorder();obs=SimpleNamespace(sequence=12);actor=object()
  with patch.object(BalanceOnlyPolicy,'act',return_value=37) as f:
   original=BalanceOnlyPolicy.act
   with ti.instrument_actor(r):self.assertEqual(BalanceOnlyPolicy.act(actor,obs),37)
   self.assertIs(BalanceOnlyPolicy.act,original);f.assert_called_once_with(actor,obs)
  with patch.object(BalanceOnlyPolicy,'act',side_effect=ValueError('guard')):
   with self.assertRaisesRegex(ValueError,'guard'):
    with ti.instrument_actor(r):BalanceOnlyPolicy.act(actor,obs)
  self.assertEqual(r.snapshot()['threads'][0]['events'][-1][-1],False)
 def test_rig_wrappers_never_connect_and_preserve_wait_fetch_step(self):
  r=ti.TimingRecorder();rig=ti.InstrumentedRig('/unused',timings=r);state=SimpleNamespace(unwrapped_tick=22)
  with patch.object(Rig,'wait_state',return_value=state) as f:
   self.assertIs(rig.wait_state(after_tick=12,timeout=.1),state);f.assert_called_once_with(after_tick=12,timeout=.1)
  with patch.object(Rig,'control_observation',return_value=SimpleNamespace(sequence=22)) as f:
   self.assertEqual(rig.control_observation().sequence,22);f.assert_called_once()
  with patch.object(Rig,'step',side_effect=RuntimeError('fault')) as f:
   with self.assertRaisesRegex(RuntimeError,'fault'):rig.step(SimpleNamespace(observation_sequence=22,sequence=4))
   f.assert_called_once()
  self.assertFalse(rig._connected)
 def test_condition_wakes_and_records_without_changing_predicate(self):
  r=ti.TimingRecorder();rig=SimpleNamespace(_state=None);c=ti.TimingCondition(r,rig);ready=threading.Event();done=[]
  def waiter():
   with c:
    ready.set()
    while rig._state is None:c.wait(.2)
    done.append(rig._state.tick)
  thread=threading.Thread(target=waiter);thread.start();ready.wait(.5)
  with c:rig._state=SimpleNamespace(tick=10);c.notify_all()
  thread.join(.5);self.assertEqual(done,[10]);self.assertFalse(thread.is_alive())
  stages=[e[0] for t in r.snapshot()['threads'] for e in t['events']];self.assertIn('condition.wait',stages);self.assertIn('condition.notify_all',stages)
 def test_trial_duration_accepts60_rejects_over_and_nan_before_io(self):
  m=load('trial-timed-v2')
  a=m.parse_args(['inspect','--out','/unused','--duration','60']);self.assertEqual(a.duration,60)
  for v in ['60.1','nan','inf','0']:
   with self.assertRaises(SystemExit):m.parse_args(['inspect','--out','/unused','--duration',v])
 def test_memory_records_are_snapshotted_after_close_and_gil_restored(self):
  m=load('trial-timed-v2');Info=make_dataclass('Info',[('encoder_upright_raw',int)]);State=make_dataclass('State',[('tick',int)])
  class FakeRig:
   closed=False;state=State(10);session=SimpleNamespace(session_id='offline')
   def __enter__(self):return self
   def __exit__(self,*args):self.closed=True
   def stop(self):pass
   def get_info(self):return Info(537)
   def _stopped_healthy(self):return self.state
   def get_parameters(self):return {}
   @property
   def records(self):
    assert self.closed,'memory dump preceded Rig.close'
    return deque([{'type':'offline-test'}],maxlen=100000)
  fake=FakeRig();original=sys.getswitchinterval()
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp)/'trial'
   with patch.object(m,'InstrumentedRig',return_value=fake) as factory,patch.object(m.time,'sleep'),patch('builtins.print'):
    self.assertEqual(m.main(['inspect','--out',str(out),'--switch-ms','1','--no-logger','--no-mirror']),0)
   self.assertIsNone(factory.call_args.kwargs['log_dir']);self.assertIsNone(factory.call_args.kwargs['vision_publisher'])
   self.assertIn('offline-test',(out/'rig-memory-offline.jsonl').read_text())
  self.assertEqual(sys.getswitchinterval(),original)
 def test_zero_options_do_not_widen_lease_and_default_workers_stay_on(self):
  m=load('zero-timing-v2');a=m.parse_args(['--out','/unused'])
  self.assertFalse(a.no_mirror);self.assertFalse(a.no_logger)
  self.assertEqual(m.LEASE_MS,20)
  self.assertTrue(m.parse_args(['--out','/unused','--no-mirror','--no-logger']).no_logger)

if __name__=='__main__':unittest.main()
