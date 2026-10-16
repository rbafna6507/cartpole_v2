"""Deterministic late-action ERR / STOP acknowledgement interleavings.

No transport or timing thread: real Rig command, protocol acceptance, error
latching, snapshot and STOP confirmation operate on scripted firmware replies.
"""
import time
import pytest
from cartpole_sdk.rig import Rig,RigError
from cartpole_sdk.rig.protocol import State


class StopRepliesRig(Rig):
    def __init__(self,*,ack=True,disabled=True,already_latched=True):
        super().__init__('scripted-stop',command_timeout=.01)
        self._connected=True;self._handshake=True
        self.ack=ack;self.disabled=disabled;self.sent=[];self.injected=False
        self.error=RigError('executor fault 1') if already_latched else None
        self.initial_error=self.error
        self._state=State(sid=self._sid,tick=100,us=100_000,mode=4,flags=13,
            theta=3.14,angle_hat=3.14,omega=0.,x=0.,velocity=0.,acceleration=0.,
            demand=0.,last_seq=1,fault=1,misses=0,dropped=0,brake_direction=0,
            received_ns=time.monotonic_ns(),unwrapped_tick=100,unwrapped_us=100_000)
        self._state_version=1;self._history[100]=self._state

    def reply(self,payload):self._accept(payload,time.monotonic_ns())

    def publish(self):
        mode,flags=(4,13) if self.disabled else (12,15)
        self.reply(f'V2 S {self._sid} 104 104000 {mode} {flags} 3.14 3.14 0 0 0 0 0 1 1 0 0 0')

    def _send(self,payload):
        self.sent.append(payload)
        parts=payload.split()
        if parts[1]=='STOP':
            if not self.injected:
                self.injected=True
                # The previously transmitted A arrived after its action lease
                # expired. Its untagged ERR can arrive during the STOP exchange.
                self.reply(f'V2 ERR {self._sid} mode')
            # Acknowledgements for unrelated commands never confirm STOP.
            self.reply(f'V2 OK {self._sid} RATE')
            if self.ack:self.reply(f'V2 OK {self._sid} STOP')
            self.publish()
        elif parts[1]=='STATUS':self.publish()
        else:self.reply(f'V2 ERR {self._sid} mode')


@pytest.mark.parametrize('already_latched',[True,False])
def test_late_action_error_does_not_hide_stop_ack_and_disabled_confirmation(already_latched):
    rig=StopRepliesRig(already_latched=already_latched)
    rig.stop()
    assert not rig.state.enabled and rig.state.mode==4
    assert rig.error is not None
    if already_latched:assert rig.error is rig.initial_error
    else:assert 'executor error: mode' in str(rig.error)
    assert any(' STATUS ' in payload for payload in rig.sent)
    assert rig._active is False and rig._deadline_ns is None
    before=len(rig.sent)
    with pytest.raises(RigError,match='latched rig error'):rig.arm(.1)
    assert len(rig.sent)==before


def test_disabled_state_and_unrelated_ok_do_not_replace_missing_stop_ack():
    rig=StopRepliesRig(ack=False)
    with pytest.raises(RigError,match='STOP acknowledgement timeout'):rig.stop()
    assert rig.error is rig.initial_error
    assert not rig.state.enabled
    assert not any(' STATUS ' in payload for payload in rig.sent)


def test_stop_ack_does_not_replace_verified_disabled_state():
    rig=StopRepliesRig(disabled=False)
    with pytest.raises(RigError,match='STOP state confirmation timeout'):rig.stop()
    assert rig.error is rig.initial_error
    assert rig.state.enabled


def test_non_stop_command_still_rejects_untagged_error_immediately():
    rig=StopRepliesRig()
    with pytest.raises(RigError,match='executor rejected RATE: mode'):
        rig._command('RATE',250,allow_error=True)
    assert rig.error is rig.initial_error
