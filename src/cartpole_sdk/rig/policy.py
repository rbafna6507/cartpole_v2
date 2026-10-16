"""Trusted host policy runner. Untrusted submissions belong in a separate broker.

Factories are explicit Python callables supplied by trusted operator code; no
module/path imports or user code loading occur here. The preserved 1kHz reference
policy is not selected automatically at a slower telemetry rate.
"""
import math
import time
from cartpole_sdk.contracts import (Acceleration, ActionRequest, Channel,
                                    ValidationError, select_channels)

class ZeroAccelerationPolicy:
    """Bounded commissioning example; it does not swing up or balance."""
    def __init__(self, channels):
        self.channels=channels
    def reset(self, session):
        pass
    def act(self, observation):
        select_channels(observation,self.channels,now_ns=observation.available_ns,max_age_ns=20_000_000)
        return Acceleration(0.)

def run_policy(rig, policy_factory, *, channels: tuple[Channel,...], duration_s=1.,
               ttl_ms=20, max_acceleration=.25):
    """Explicitly arm and execute a trusted policy with selected sensor channels.

    Observation and request clocks are the board clock. This runner is paced by
    fresh telemetry and bounds wall duration; firmware still owns lease expiry.
    Every return/exception stops in finally. None does not renew the last action.
    The default commissioning ceiling is intentionally small and configurable
    only by trusted operator code, within the executor's absolute limit.
    """
    rig._duration(duration_s)
    if not callable(policy_factory):
        raise ValidationError('policy_factory must be an explicit trusted callable')
    if type(channels) is not tuple or not channels or not all(isinstance(c,Channel) for c in channels):
        raise ValidationError('policy requires explicit source/frame channels')
    if type(ttl_ms) is not int or not 1<=ttl_ms<=50:
        raise ValidationError('TTL must be 1..50 integer milliseconds')
    if type(max_acceleration) not in (int,float) or not math.isfinite(max_acceleration) or not 0<max_acceleration<=25:
        raise ValidationError('commissioning acceleration bound must be positive and <=25')
    if rig.rate_hz == 0 or 1000/rig.rate_hz >= ttl_ms:
        raise ValidationError('telemetry interval must be shorter than anchored action TTL')
    failure=None
    try:
        observation=rig.observation()
        select_channels(observation,channels,now_ns=observation.available_ns,max_age_ns=20_000_000)
        policy=policy_factory(channels)
        if not callable(getattr(policy,'reset',None)) or not callable(getattr(policy,'act',None)):
            raise ValidationError('factory must return a Policy')
        policy.reset(rig.session)
        rig._record('policy_start',channels=[dict(entity=c.entity,quantity=c.quantity,source=c.source,frame_id=c.frame_id) for c in channels],
                    policy=type(policy).__name__,duration_s=duration_s,ttl_ms=ttl_ms,max_acceleration=max_acceleration)
        rig.arm(duration_s)
        deadline=rig._deadline_ns/1e9-min(.01,duration_s*.25)
        sequence=0
        while time.monotonic()<deadline:
            observation=rig.observation()
            select_channels(observation,channels,now_ns=observation.available_ns,max_age_ns=20_000_000)
            intent=policy.act(observation)
            if intent is None and getattr(policy, 'fault_reason', None):
                raise ValidationError(f'host policy fault: {policy.fault_reason}')
            if intent is not None:
                if not isinstance(intent,Acceleration) or abs(intent.acceleration_m_s2)>max_acceleration:
                    raise ValidationError('policy output exceeds commissioning bound or is not Acceleration')
                sequence+=1
                request=ActionRequest(observation.session_id,observation.clock_id,sequence,observation.sequence,
                                      observation.available_ns,observation.available_ns+ttl_ms*1_000_000,
                                      intent.acceleration_m_s2)
                rig.step(request)
            remaining=deadline-time.monotonic()
            if remaining<=0:
                break
            try:
                rig.wait_state(after_tick=observation.sequence,timeout=min(remaining,.1))
            except TimeoutError:
                if time.monotonic()>=deadline:
                    break
                raise
    except BaseException as exc:
        failure=exc
        rig._record('policy_failure',reason=str(exc))
        raise
    finally:
        try:
            rig.stop()
        except Exception as exc:
            rig._record('stop_failure',reason=str(exc))
            if failure is None:
                raise
        finally:
            rig._record('policy_end')


def run_host_controller(rig, *, mode, duration_s=10.):
    """Trusted experimental host auto/bal, using a stopped live v6 readback.

    No calibration, parameter write, home or rehome is implicit. Native auto/bal
    are separate commands. The MCU still owns its 1 kHz external-mode governor.
    """
    from dataclasses import asdict, fields
    from cartpole_sdk.control.parameters import ControllerParameters
    from cartpole_sdk.policies import HostPolicyParameters, HostRatePolicy
    if mode not in ('auto', 'bal') or rig.rate_hz not in (100, 250):
        raise ValidationError('host controller requires auto/bal and 100 or 250 Hz telemetry')
    rig._duration(duration_s)
    rig._stopped_healthy()
    values = rig.get_parameters()
    if set(values) != {f.name for f in fields(ControllerParameters)}:
        raise ValidationError('host controller requires the complete v6 live parameter catalog')
    settings = HostPolicyParameters.from_controller(ControllerParameters(**values), start_mode=mode)
    channels = (Channel('cart','position','step','cart-step-home'),
                Channel('cart','velocity','step','cart-step-home'),
                Channel('pole','angle','magnetic','encoder-zero'),
                Channel('pole','angular_velocity','magnetic','encoder-zero'))
    rig._record('host_controller', mode=mode, rate_hz=rig.rate_hz,
                controller_parameters=values, policy_parameters=asdict(settings),
                hardware_validated=False)
    run_policy(rig, lambda selected: HostRatePolicy(selected, rate_hz=rig.rate_hz,
               parameters=settings, start_mode=mode), channels=channels,
               duration_s=duration_s, ttl_ms=20, max_acceleration=settings.max_acceleration_m_s2)
