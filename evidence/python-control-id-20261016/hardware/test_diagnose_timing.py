"""Offline only: real runner with scripted clock, no serial transport."""
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import diagnose_timing_stopfix as diagnostic

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tests'))
from test_rig_console import ScriptedClock,ScriptedConsoleRig


def test_trace_preserves_value_and_exact_exception():
    trace=diagnostic.MemoryTrace(4);marker=object();error=RuntimeError('original')
    assert trace.call(0,lambda:marker) is marker
    def fails():raise error
    with pytest.raises(RuntimeError) as caught:trace.call(1,fails)
    assert caught.value is error
    assert trace.count==2
    assert list(trace.columns[9][:2])==[0,1]
    for i in range(2):
        assert trace.columns[3][i]>=trace.columns[1][i]
        assert trace.columns[4][i]>=trace.columns[2][i]


def test_overflow_counts_without_changing_values_or_errors():
    trace=diagnostic.MemoryTrace(1)
    assert trace.call(0,lambda:1)==1
    assert trace.call(1,lambda:2)==2
    error=RuntimeError('original')
    def fails():raise error
    with pytest.raises(RuntimeError) as caught:trace.call(2,fails)
    assert caught.value is error and trace.count==1 and trace.dropped==2


def test_guarded_always_stops_and_does_not_mask_original_exception():
    calls=[];error=RuntimeError('original')
    def stop():calls.append('STOP');raise ValueError('stop failed')
    def operation():raise error
    report={}
    with pytest.raises(RuntimeError) as caught:
        diagnostic.guarded(SimpleNamespace(stop=stop),operation,report)
    assert caught.value is error and calls==['STOP']
    assert report['stop_confirmed'] is False and 'stop failed' in report['stop_failure']


def test_source_pinning_rejects_mismatch_before_connection(monkeypatch):
    monkeypatch.setattr(diagnostic,'EXPECTED_SOURCE_SHA256',{'cartpole_sdk/rig/policy.py':'incorrect'})
    with pytest.raises(RuntimeError,match='source mismatch'):diagnostic.load_sdk(ROOT/'src')


@pytest.mark.parametrize('case,intervals,expect_failure', [('zero',(4,)*20,False),('zero',(24,),True),('observe',(8,12,16,4)*5,False)])
def test_real_runner_values_stop_and_disabled_counterpart(case,intervals,expect_failure):
    modules=diagnostic.load_sdk(ROOT/'src')
    clock=ScriptedClock();clock.now_ns=0
    rig=ScriptedConsoleRig('inert-test',clock=clock,intervals=intervals,rate_hz=250)
    rig.connect();rig._state=replace(rig._state,theta=3.141592653589793,angle_hat=3.141592653589793,
        omega=0.,x=0.,flags=205)
    rig._info=SimpleNamespace(firmware='executor-v6-measuredrail',encoder_upright_raw=330)
    # Preflight uses dataclasses asdict for actual firmware info; substitute the
    # info dataclass expected by SDK rather than weakening preflight.
    from cartpole_sdk.rig.protocol import ExecutorInfo
    import inspect
    values={name:0 for name in inspect.signature(ExecutorInfo).parameters}
    values.update(firmware='executor-v6-measuredrail',encoder_upright_raw=330,sid=rig._sid)
    rig._info=ExecutorInfo(**values)
    trace=diagnostic.MemoryTrace();report={}
    args=SimpleNamespace(case=case,rate=250,seconds=.06,shadow_feedback=False)
    failure=None
    with patch('cartpole_sdk.rig.policy.time',clock),patch('cartpole_sdk.rig.client.time',clock),patch.object(diagnostic,'time',SimpleNamespace(
            monotonic=clock.monotonic,monotonic_ns=clock.monotonic_ns,thread_time_ns=__import__('time').thread_time_ns)):
        try:diagnostic.guarded(rig,lambda:diagnostic.execute(rig,trace,args,modules,report),report)
        except Exception as exc:failure=exc
        finally:rig.close()
    assert (failure is not None)==expect_failure
    if failure:assert 'lease expired' in str(failure)
    assert report['stop_confirmed'] and rig.commands[-1][1]=='STOP'
    requests=[r['request'] for r in rig.records if r['type']=='action_request']
    if case=='zero':
        assert requests
        assert all(r['acceleration_m_s2']==0. and r['expires_at_ns']-r['issued_at_ns']==20_000_000 for r in requests)
        assert 2 in trace.columns[0][:trace.count]
    else:
        assert not requests and not any(c[1] in ('ARM','A','MODE') for c in rig.commands)
        assert 2 not in trace.columns[0][:trace.count]
    assert set(trace.columns[0][:trace.count])>={0,1,3}


def test_independent_logging_and_mirror_switches_parse_before_any_connection(monkeypatch):
    seen=[]
    def stop_before_connect(source):seen.append(source);raise RuntimeError('offline stop before connection')
    monkeypatch.setattr(diagnostic,'load_sdk',stop_before_connect)
    for switches in (['--no-log'],['--no-mirror'],['--no-log','--no-mirror']):
        with pytest.raises(RuntimeError,match='offline stop before connection'):
            diagnostic.main(['observe','--sdk-src',str(ROOT/'src'),*switches])
    assert len(seen)==3


def test_after_stop_summary_counts_gaps_and_cpu_time():
    trace=diagnostic.MemoryTrace()
    for sequence,board in ((0,0),(8,8_000_000),(20,20_000_000),(36,36_000_000)):
        trace.call(0,lambda:SimpleNamespace(sequence=sequence,available_ns=board))
    summary=trace.summary(250)
    assert summary['observations']==4
    assert summary['max_observation_gap_ns']==16_000_000
    assert summary['gaps_above_1_5_periods']==3
    assert summary['gaps_above_3_periods']==1
    assert summary['stage_max_wall_ns']['observe']>=0
    assert summary['stage_max_cpu_ns']['observe']>=0
