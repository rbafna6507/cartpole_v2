from dataclasses import replace
import json
import threading
import time
import pytest
from cartpole_sdk.rig.protocol import State, ExecutorInfo
from cartpole_sdk.sensing.telemetry import EncoderPublisher, encoder_packet


def state():
    return State(123,20,20000,0,5,.1,.09,.2,.03,0,0,0,0,0,0,0,0,
                 received_ns=1_000_000_000,unwrapped_tick=20,unwrapped_us=20000)


def info():
    return ExecutorInfo(123,'executor-v4-rehome',370,True,32,0,0,0,.26,900_000_000)


def test_legacy_packet_health_uses_current_state_and_preserves_explicit_clocks():
    packet=encoder_packet(state(),info(),sequence=1,generation=0)
    assert packet['v']==1 and packet['theta']==.1 and packet['upright']==370
    assert packet['valid'] is True and packet['health']['status']=='ok'
    assert packet['host_t']==1. and packet['board_ms']==20
    assert packet['sdk_state']['unwrapped_us']==20000
    assert packet['board_clock_id']=='teensy:123'
    assert packet['health']['basis']=='current executor state flags and fault'
    for bad in (replace(state(),flags=4),replace(state(),fault=1),replace(state(),flags=261)):
        assert encoder_packet(bad,info(),sequence=2,generation=0)['valid'] is False
    assert encoder_packet(state(),None,sequence=1,generation=0)['upright'] is None


def test_submit_never_serializes_or_waits_for_network_and_latest_queue_is_bounded():
    entered=threading.Event();release=threading.Event();sent=[]
    class Socket:
        def setblocking(self,value):assert value is False
        def sendto(self,data,address):
            entered.set();release.wait(.5);sent.append(json.loads(data));return len(data)
        def close(self):pass
    pub=EncoderPublisher(socket_factory=lambda *a:Socket())
    pub.start()
    try:
        pub.submit(state(),info());assert entered.wait(.5)
        before=time.monotonic()
        for n in range(1000):pub.submit(replace(state(),unwrapped_tick=n),info())
        assert time.monotonic()-before<.1
        release.set()
        deadline=time.monotonic()+.5
        while len(sent)<2 and time.monotonic()<deadline:time.sleep(.005)
        assert sent[-1]['sdk_state']['unwrapped_tick']==999
    finally:release.set();pub.close()


def test_network_errors_only_drop_mirror_packets():
    class Socket:
        def setblocking(self,value):pass
        def sendto(self,*a):raise BlockingIOError('full')
        def close(self):pass
    pub=EncoderPublisher(socket_factory=lambda *a:Socket());pub.start()
    try:
        pub.submit(state(),info())
        deadline=time.monotonic()+.5
        while not pub.dropped and time.monotonic()<deadline:time.sleep(.005)
        assert pub.dropped==1
    finally:pub.close()


def test_optional_rig_mirror_uses_accepted_reader_state_and_info_without_extra_commands():
    from cartpole_sdk.rig import Rig
    from test_rig import Firmware, FDTransport
    fw=Firmware();seen=[]
    class Mirror:
        def start(self):pass
        def submit(self,state,info):seen.append((state,info))
        def close(self):pass
    try:
        with Rig(fw.port,transport_factory=FDTransport,vision_publisher=Mirror()) as rig:
            assert seen and seen[-1][0].sid==int(rig.session.session_id)
            original_receipt=rig.state.received_ns
            rig.get_info()
            assert seen[-1][1].encoder_upright_raw==270
            assert seen[-1][0].received_ns>=original_receipt
        assert [p[1] for p in fw.commands].count('HELLO')==1
        assert not any(p[1] in ('MODE','ARM') for p in fw.commands)
    finally:fw.close()


def test_console_reads_info_before_any_motion_and_can_disable_mirror(tmp_path):
    from cartpole_sdk.rig import Rig
    from cartpole_sdk.rig.console import main
    from test_rig import Firmware, FDTransport
    fw=Firmware()
    def factory(port,**kwargs):
        assert kwargs['vision_publisher'].port==0
        return Rig(port,transport_factory=FDTransport,**kwargs)
    try:
        assert main(['--port',fw.port,'--no-vision-telemetry','--keep-board-params','--command','auto',
                     '--duration','.03','--log-dir',str(tmp_path)],rig_factory=factory)==0
        commands=[p[1] for p in fw.commands]
        assert commands.index('INFO')<commands.index('MODE')
    finally:fw.close()


def test_calibration_quarantines_reference_until_a_new_rig_session():
    from concurrent.futures import ThreadPoolExecutor
    from cartpole_sdk.rig import Rig
    from test_rig import FDTransport
    from test_rig_calibration import CalibrationFirmware
    fw=CalibrationFirmware();seen=[]
    class Mirror:
        def start(self):pass
        def submit(self,state,info):seen.append((state,info))
        def close(self):pass
    try:
        with Rig(fw.port,transport_factory=FDTransport,vision_publisher=Mirror()) as rig:
            rig.get_info();assert seen[-1][1].encoder_upright_raw==3485
            with ThreadPoolExecutor(1) as pool:
                result=pool.submit(rig.calibrate_encoder)
                assert fw.started.wait(.5)
                boundary=len(seen)
                assert result.result(timeout=1).encoder_upright_raw==3210
            rig.get_info();rig._snapshot()
            assert seen[boundary:]
            assert all(info is None for _,info in seen[boundary:])
            assert rig.get_info().encoder_upright_raw==3210
        seen.clear()
        with Rig(fw.port,transport_factory=FDTransport,vision_publisher=Mirror()) as rig:
            rig.get_info();rig._snapshot()
            assert seen[-1][1].encoder_upright_raw==3210
    finally:fw.close()
