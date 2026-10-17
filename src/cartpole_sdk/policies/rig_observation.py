"""Shared, dependency-free encoder for rig SDK and governed Gym policy inputs.

Only explicit channels are read. This module imports no simulator or device
client; it can run on the policy host. The encoder preserves validity and age,
using finite zeros for missing values. The trusted runner/policy must still
enforce freshness and reject unusable channels before sending hardware actions.
"""
import math

from cartpole_sdk.contracts import Channel, Observation, ValidationError

QUANTITIES = ('position', 'velocity', 'angle', 'angular_velocity', 'acceleration', 'brake_direction')
STATE_FIELDS = ('x_m', 'commanded_v_m_s', 'sin_angle', 'cos_angle',
                'filtered_omega_rad_s', 'commanded_a_m_s2', 'brake_direction')
SCHEMA = 'cartpole-rig-observation-v1'


def rig_channels(*, angle_source='raw'):
    """Explicit channels from Rig.control_observation(), retaining raw by default."""
    if angle_source not in ('raw', 'filtered'):
        raise ValidationError('angle_source must be raw or filtered')
    return tuple(Channel(entity, quantity, source, frame) for entity, quantity, source, frame in (
        ('cart', 'position', 'step', 'cart-step-home'),
        ('cart', 'velocity', 'step', 'cart-step-home'),
        ('pole', 'angle', 'magnetic' if angle_source == 'raw' else 'magnetic_filtered', 'encoder-zero'),
        ('pole', 'angular_velocity', 'magnetic', 'encoder-zero'),
        ('cart', 'acceleration', 'step', 'cart-step-home'),
        ('cart', 'brake_direction', 'step', 'cart-step-home'),
    ))


def simulation_channels():
    return tuple(Channel('pole' if q in ('angle', 'angular_velocity') else 'cart',
                         q, 'simulation', 'sim:upright+x') for q in QUANTITIES)


def encode_rig_observation(observation, channels):
    """Return list-valued state/valid/age_s in the fixed seven-feature schema.

    No inference about source/frame is made. Missing channels are unknown;
    invalid samples preserve their age when known. Age is in the observation's
    declared clock, not host receipt time. Raw angle and filtered angle are
    separate channel selections with the same numeric encoding.
    """
    if not isinstance(observation, Observation):
        raise ValidationError('expected SDK Observation')
    if (type(channels) is not tuple or len(channels) != len(QUANTITIES) or
            not all(isinstance(c, Channel) for c in channels) or
            tuple(c.quantity for c in channels) != QUANTITIES):
        raise ValidationError('choose explicit x, velocity, angle, rate, acceleration, brake channels')
    available = {s.channel: s for s in observation.samples}
    state, valid, ages = [], [], []
    for index, transform in ((0, float), (1, float), (2, math.sin), (2, math.cos),
                             (3, float), (4, float), (5, float)):
        sample = available.get(channels[index])
        usable = sample is not None and sample.validity == 'valid' and sample.value is not None
        state.append(transform(sample.value) if usable else 0.)
        valid.append(int(usable))
        ages.append(-1. if sample is None or sample.effective_ns is None else
                    (observation.available_ns-sample.effective_ns)/1e9)
    return {'state': state, 'valid': valid, 'age_s': ages}
