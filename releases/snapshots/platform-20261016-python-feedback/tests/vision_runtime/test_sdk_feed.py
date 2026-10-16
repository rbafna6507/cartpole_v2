import copy
from cartpole_vision import sdk_feed


def packet(seq=1, t=10):
    return dict(schema="cartpole-sdk-shadow-v1", session_id="session", clock_id="boot:test", sequence=seq,
                host_t=t, observation={"session_id":"session", "clock_id":"boot:test", "sequence":seq, "available_ns":int(t*1e9), "availability_basis":"host receipt", "samples":[]},
                diagnostics={"status": "not_configured"}, commissioned=False, control_eligible=False)


def test_sdk_shadow_preserves_identity_and_rejects_bad_or_stale_packets():
    feed = sdk_feed.SDKFeed(None)
    assert feed.snapshot(now=10)["status"] == "not_configured"
    assert feed.accept(packet(), now=10)
    assert not feed.accept(packet(), now=10)
    assert not feed.accept(packet(2, 8), now=10)
    assert not feed.accept({**packet(2), "commissioned": True}, now=10)
    result = feed.snapshot(now=10.01)
    assert result["packet"]["clock_id"] == "boot:test"
    assert result["age_s"] < .02
    assert feed.snapshot(now=11)["status"] == "stale"


def test_sdk_history_resets_across_sessions_and_is_bounded():
    feed = sdk_feed.SDKFeed(None)
    for seq in range(4100): assert feed.accept(packet(seq, 10 + seq*.001), now=10+seq*.001)
    assert len(feed.snapshot(now=14.1)["samples"]) <= 2048
    new = {**packet(0, 14.2), "session_id": "restart"}
    new["observation"]["session_id"] = "restart"
    assert feed.accept(new, now=14.2)
    assert len(feed.snapshot(now=14.2)["samples"]) == 1


def test_sdk_freshness_uses_original_producer_time():
    feed=sdk_feed.SDKFeed(None)
    assert feed.accept(packet(1,10),now=10.49)
    assert feed.snapshot(now=10.51)["status"] == "stale"


def test_sdk_rejects_missing_observation_and_clears_calibration_history():
    feed=sdk_feed.SDKFeed(None)
    assert not feed.accept({**packet(), "observation":None},now=10)
    p=packet();p["diagnostics"]["calibration_id"]="a"
    assert feed.accept(p,now=10)
    p=packet(2,10.01);p["diagnostics"]["calibration_id"]="b"
    assert feed.accept(p,now=10.01)
    assert len(feed.snapshot(now=10.01)["samples"]) == 1
