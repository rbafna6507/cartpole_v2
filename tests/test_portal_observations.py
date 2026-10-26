"""Portal policies can select all available SDK feedback without relabeling it."""
from cartpole_sdk.portal.worker import HardwareBridge, SimulationBridge
from cartpole_sdk.rig import Rig
from test_rig import FDTransport, Firmware


def test_hardware_bridge_exposes_raw_filtered_and_governor_feedback():
    fw=Firmware();fw.flags |=8
    try:
        with Rig(fw.port,transport_factory=FDTransport,command_timeout=.2) as rig:
            bridge=HardwareBridge(rig=rig)
            obs=bridge.prepare(.1,'test')
            channels={(s.quantity,s.source) for s in obs.samples}
            assert ('angle','magnetic') in channels
            assert ('angle','magnetic_filtered') in channels
            assert ('acceleration','step') in channels
            assert ('brake_direction','step') in channels
            assert all(s.acquired_ns==obs.available_ns for s in obs.samples)
            assert not any(c[1] in ('ARM','HOME','MODE','CENTER') for c in fw.commands)
    finally:fw.close()


def test_simulation_bridge_preserves_available_governor_samples():
    bridge=SimulationBridge()
    try:
        obs=bridge.prepare(.1,'test')
        channels={(s.quantity,s.source) for s in obs.samples}
        assert ('acceleration','simulation') in channels
        assert ('brake_direction','simulation') in channels
        assert all(s.source=='simulation' for s in obs.samples)
        assert obs.sequence==bridge.env.sdk_observation.sequence
    finally:bridge.close()


def test_portal_uses_shared_versioned_development_profile():
    from cartpole_sdk.sim.profiles import PROFILE_ID, PROFILE_SHA256, make_profile_env
    bridge=SimulationBridge()
    reference=make_profile_env(seconds=.1)
    try:
        actual=bridge.prepare(.1,'test-profile')
        reference.reset(seed=0)
        assert actual.samples==reference.sdk_observation.samples
        assert bridge.diagnostics()['profile_id']==PROFILE_ID
        assert bridge.diagnostics()['profile_sha256']==PROFILE_SHA256
        actual=bridge.advance(.1,1)
        reference.step([.1])
        assert actual.samples==reference.sdk_observation.samples
    finally:bridge.close();reference.close()
