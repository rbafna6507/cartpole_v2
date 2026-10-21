"""Fake-Rig checks; no physical transport or devices."""
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tests'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_balance_hardware import saved_actor,rehearsal
from test_neural_runner import DeadlineAwareShadowRig
from cartpole_sdk.contracts import ValidationError
from cartpole_sdk.learning.balance_hardware import BalanceOnlyPolicy,run_balance_policy
from settling_balance import run_settling_balance_policy

def run(rig,actor,**kwargs):
 return run_settling_balance_policy(rig,actor,expected_upright_raw=123,development_only=True,execute=True,
  duration_s=kwargs.pop('duration_s',.3),max_acceleration=.25,settle_ms=kwargs.pop('settle_ms',200),**kwargs)
def requests(rig):return [r['request'] for r in rig.records if r['type']=='action_request']
def stopped(rig):assert rig.commands[-1][1]=='STOP' and not rig.state.enabled

def test_twenty_zero_commands_then_exact_actor_with_leases_and_no_early_inference(tmp_path):
 actor=saved_actor(tmp_path,demand=.1,mode='filtered');before=actor.read_bytes()
 with rehearsal() as rig:
  calls=[];original=BalanceOnlyPolicy.predict_encoded
  def predict(self,encoded):
   if rig.state.enabled:calls.append(rig.clock.now_ns)
   return original(self,encoded)
  with patch.object(BalanceOnlyPolicy,'predict_encoded',predict):result=run(rig,actor)
  sent=requests(rig);origin=sent[0]['issued_at_ns']
  assert len(sent)>20 and [r['acceleration_m_s2'] for r in sent[:20]]==[0.]*20
  assert all(r['acceleration_m_s2']==.1 for r in sent[20:])
  assert sent[20]['issued_at_ns']-origin==200_000_000
  assert calls and min(calls)>=200_000_000
  assert all(r['expires_at_ns']-r['issued_at_ns']==20_000_000 for r in sent)
  transfers=[r for r in rig.records if r['type']=='startup_settling_transfer'];assert len(transfers)==1 and transfers[0]['elapsed_ns']==200_000_000
  assert result['settle_ms']==200 and result['duration_s']==.3
  recorded=[r for r in rig.records if r['type']=='startup_settling_command']
  assert [r['raw_acceleration_m_s2'] for r in recorded]==[r['acceleration_m_s2'] for r in sent]
  assert {c[1] for c in rig.commands}=={'ARM','A','STOP'};stopped(rig)
 assert actor.read_bytes()==before

def test_default_zero_setting_preserves_immediate_command_sequence(tmp_path):
 actor=saved_actor(tmp_path,demand=.1,mode='filtered');outputs=[]
 for wrapper in (False,True):
  with rehearsal() as rig:
   if wrapper:run(rig,actor,settle_ms=0,duration_s=.04)
   else:run_balance_policy(rig,actor,expected_upright_raw=123,development_only=True,execute=True,duration_s=.04,max_acceleration=.25)
   outputs.append(requests(rig));assert not any(r['type'].startswith('startup_settling') for r in rig.records);stopped(rig)
 assert [(r['issued_at_ns'],r['acceleration_m_s2'],r['expires_at_ns']) for r in outputs[0]]==[(r['issued_at_ns'],r['acceleration_m_s2'],r['expires_at_ns']) for r in outputs[1]]

@pytest.mark.parametrize('state',[dict(theta=.08),dict(angle_hat=.08),dict(omega=.16),dict(x=.016),dict(velocity=.026),dict(brake_direction=1)])
def test_normal_full_start_guard_runs_before_arm(tmp_path,state):
 actor=saved_actor(tmp_path,demand=.1,mode='filtered')
 with rehearsal(state=state) as rig:
  with pytest.raises(ValidationError,match='balance-only'):run(rig,actor)
  assert not any(c[1] in ('ARM','A') for c in rig.commands);stopped(rig)

def test_settling_allows_bounded_enable_transient_then_full_start_transfer(tmp_path):
 class Transient(DeadlineAwareShadowRig):
  def _command_state(self,command,*args,**kwargs):
   super()._command_state(command,*args,**kwargs)
   if command=='ARM':self._state=replace(self._state,theta=.10,angle_hat=.09,omega=2.);self._history[self._state.unwrapped_tick]=self._state
  def wait_state(self,**kwargs):
   super().wait_state(**kwargs)
   if self.clock.now_ns>=200_000_000:self._state=replace(self._state,theta=.02,angle_hat=.02,omega=.1);self._history[self._state.unwrapped_tick]=self._state
   return self._state
 actor=saved_actor(tmp_path,demand=.1,mode='filtered')
 with rehearsal(rig_type=Transient) as rig:
  run(rig,actor);assert [r['acceleration_m_s2'] for r in requests(rig)[:20]]==[0.]*20;assert requests(rig)[20]['acceleration_m_s2']==.1;stopped(rig)

@pytest.mark.parametrize('state',[dict(theta=.08),dict(angle_hat=.08),dict(omega=.16)])
def test_transfer_requires_full_start_guard_without_extending_settle(tmp_path,state):
 class NotSettled(DeadlineAwareShadowRig):
  def wait_state(self,**kwargs):
   super().wait_state(**kwargs)
   if self.clock.now_ns>=200_000_000:self._state=replace(self._state,**state);self._history[self._state.unwrapped_tick]=self._state
   return self._state
 actor=saved_actor(tmp_path,demand=.1,mode='filtered')
 with rehearsal(rig_type=NotSettled) as rig:
  with pytest.raises(ValidationError,match='balance-only'):run(rig,actor)
  assert len(requests(rig))==20 and all(r['acceleration_m_s2']==0 for r in requests(rig));assert rig.clock.now_ns==200_000_000;stopped(rig)

@pytest.mark.parametrize('problem',['fault','unhealthy','raw_missing','selected_missing','raw_skew','raw_stale','angle','rate','position','speed','brake','reference'])
def test_settling_faults_fail_closed_after_one_zero(tmp_path,problem):
 class Faulted(DeadlineAwareShadowRig):
  def wait_state(self,**kwargs):
   super().wait_state(**kwargs)
   changes={'fault':dict(fault=4),'unhealthy':dict(flags=self._state.flags&~1),'angle':dict(theta=.175),'rate':dict(omega=3.01),
    'position':dict(x=.016),'speed':dict(velocity=.026),'brake':dict(brake_direction=1)}
   if problem in changes:self._state=replace(self._state,**changes[problem]);self._history[self._state.unwrapped_tick]=self._state
   if problem=='reference':self._info.encoder_upright_raw=124
   return self._state
  def control_observation(self):
   o=super().control_observation()
   if self.clock.now_ns<=0:return o
   if problem in ('raw_skew','raw_stale') and self.clock.now_ns<30_000_000:return o
   samples=[]
   for s in o.samples:
    raw=s.quantity=='angle' and s.source=='magnetic'
    if problem=='raw_missing' and raw:continue
    if problem=='selected_missing' and s.quantity=='acceleration':continue
    if raw and problem in ('raw_skew','raw_stale'):
     s=replace(s,effective_ns=o.available_ns-(10_000_001 if problem=='raw_skew' else 20_000_001))
    samples.append(s)
   return replace(o,samples=tuple(samples))
 actor=saved_actor(tmp_path,demand=.1,mode='filtered')
 with rehearsal(rig_type=Faulted) as rig:
  with pytest.raises((ValidationError,RuntimeError)):run(rig,actor)
  assert len(requests(rig))==(3 if problem in ('raw_skew','raw_stale') else 1)
  assert all(r['acceleration_m_s2']==0 for r in requests(rig));stopped(rig)

def test_settling_cadence_gap_keeps_existing_five_to_fifteen_ms_bound(tmp_path):
 actor=saved_actor(tmp_path,demand=.1,mode='filtered')
 with rehearsal() as rig:
  rig.intervals=iter([16])
  with pytest.raises(ValidationError,match='cadence'):run(rig,actor)
  assert len(requests(rig))==1;stopped(rig)

@pytest.mark.parametrize('settle_ms,duration',[(True,.3),(-1,.3),(100,.3),(201,.3),(200,.2),(200,.24),(200,61.)])
def test_invalid_phase_or_total_duration_rejected_before_arm(tmp_path,settle_ms,duration):
 actor=saved_actor(tmp_path,demand=.1,mode='filtered')
 with rehearsal() as rig:
  with pytest.raises(ValidationError):run(rig,actor,settle_ms=settle_ms,duration_s=duration)
  assert not any(c[1]=='ARM' for c in rig.commands);stopped(rig)

def test_total_duration_includes_settling_and_is_not_extended(tmp_path):
 actor=saved_actor(tmp_path,demand=.1,mode='filtered')
 with rehearsal() as rig:
  run(rig,actor,duration_s=.25)
  arm=next(c for c in rig.commands if c[1]=='ARM');assert arm[-1]=='250'
  assert rig.clock.now_ns<=250_000_000 and 20<len(requests(rig))<25;stopped(rig)


def test_transfer_keeps_actor_acceleration_guard_and_does_not_reset_session_again(tmp_path):
 actor=saved_actor(tmp_path,demand=.3,mode='filtered')
 with rehearsal() as rig:
  sessions=[];original=BalanceOnlyPolicy.reset
  def reset(self,session):sessions.append(session);return original(self,session)
  with patch.object(BalanceOnlyPolicy,'reset',reset):
   with pytest.raises(ValidationError,match='acceleration'):run(rig,actor)
  assert len(sessions)==1 and len(requests(rig))==20
  assert all(r['acceleration_m_s2']==0 for r in requests(rig));stopped(rig)
