"""Opt-in Linux realtime isolation tests. No hardware imports or serial access.

Run only under trusted RR10 on one CPU, with CARTPOLE_TEST_REALTIME_CPU naming
another CPU. Normal test suites skip these privileged scheduler experiments.
"""
import os
import sys
import time
import pytest
from cartpole_sdk.contracts import Session,Observation
from cartpole_sdk.portal.sandbox import Sandbox,SandboxError

CPU=os.environ.get('CARTPOLE_TEST_REALTIME_CPU')
pytestmark=pytest.mark.skipif(sys.platform!='linux' or CPU is None,reason='explicit isolated realtime test supervisor required')
OBS=Observation('rt-test','clock',1,0,'test',())

def runtime(tmp_path,reset='pass',act='return Acceleration(0)',timeout=.01):
    path=tmp_path/'policy.py'
    path.write_text('from cartpole_sdk.contracts import Acceleration\nimport os,resource,time\nclass Policy:\n def reset(self,session):\n  '+reset.replace('\n','\n  ')+'\n def act(self,observation):\n  '+act.replace('\n','\n  ')+'\ndef create_policy():return Policy()\n')
    return Sandbox(path,cpu_affinity=int(CPU),realtime=True,wall_seconds=3,action_timeout=timeout)

def test_realtime_child_limits_cannot_be_raised_or_scheduling_changed(tmp_path):
    check="assert resource.getrlimit(resource.RLIMIT_RTTIME)==(500000,500000)\nassert resource.getrlimit(resource.RLIMIT_RTPRIO)==(1,1)\nfor attempt in (lambda:resource.setrlimit(resource.RLIMIT_RTTIME,(1000000,1000000)),lambda:os.sched_setscheduler(0,os.SCHED_RR,os.sched_param(2)),lambda:os.sched_setaffinity(0,{0})):\n try:attempt()\n except (PermissionError,ValueError):pass\n else:raise RuntimeError('restriction escaped')\nreturn Acceleration(0)"
    with runtime(tmp_path,act=check).launch() as child:
        child.reset(Session('rt-test','clock'))
        assert child.act(OBS)==0


def test_realtime_reset_cpu_burner_is_bounded_while_unarmed(tmp_path):
    began=time.monotonic()
    with runtime(tmp_path,reset='while True:pass').launch() as child:
        with pytest.raises(SandboxError):child.reset(Session('rt-test','clock'))
    assert time.monotonic()-began<2.5


def test_realtime_action_cpu_burner_hits_hard_cpu_budget(tmp_path):
    # Wider *test-only* IPC deadline proves the independent kernel CPU limit.
    with runtime(tmp_path,act='while True:pass',timeout=1.).launch() as child:
        child.reset(Session('rt-test','clock'));began=time.monotonic()
        with pytest.raises(SandboxError):child.act(OBS)
        assert time.monotonic()-began<.9


def test_realtime_sleeping_policy_cannot_evade_wall_deadline(tmp_path):
    with runtime(tmp_path,act='while True:time.sleep(.001)').launch() as child:
        child.reset(Session('rt-test','clock'));began=time.monotonic()
        with pytest.raises(SandboxError):child.act(OBS)
        assert time.monotonic()-began<.2


def test_realtime_busy_policy_still_has_ten_ms_broker_deadline(tmp_path):
    with runtime(tmp_path,act='while True:pass').launch() as child:
        child.reset(Session('rt-test','clock'));began=time.monotonic()
        with pytest.raises(SandboxError):child.act(OBS)
        assert time.monotonic()-began<.2
