"""The fixed-step firmware port must not silently consume incompatible streams."""
from dataclasses import replace
import unittest

from cartpole_sdk import Channel, Observation, Sample, Session, Topology, ValidationError
from cartpole_sdk.control.policy import ReferencePolicy

ANGLE = Channel('pole', 'angle', 'simulation', 'sim:upright+x')
POSITION = Channel('cart', 'position', 'simulation', 'sim:upright+x')
SESSION = Session('test', 'simulation')


def obs(sequence=0, time_ns=0, **angle_changes):
    angle = Sample('pole', 'angle', 'simulation', .04, 'rad', ANGLE.frame_id,
                   'test', 'valid', None, 'measured', time_ns, time_ns, time_ns)
    position = Sample('cart', 'position', 'simulation', 0., 'm', POSITION.frame_id,
                      'test', 'valid', None, 'measured', time_ns, time_ns, time_ns)
    return Observation('test', 'simulation', sequence, time_ns, 'test',
                       (replace(angle, **angle_changes), position))


class ReferencePolicyTests(unittest.TestCase):
    def policy(self, **kwargs):
        p = ReferencePolicy(ANGLE, POSITION, start_mode='upright', **kwargs)
        p.reset(SESSION)
        return p

    def test_starts_saved_controller_and_returns_governed_acceleration(self):
        p = self.policy()
        action = p.act(obs())
        self.assertIsNotNone(action)
        self.assertEqual(p.last_output.mode, 3)
        self.assertTrue(p.last_output.upright_only)
        self.assertEqual(action.acceleration_m_s2, p.last_output.acceleration)
        self.assertNotEqual(p.last_output.demand, p.last_output.acceleration)
        self.assertIsNotNone(p.act(obs(1, 1_000_000)))

    def test_bad_data_latches_no_request_until_explicit_reset(self):
        cases = ({'validity':'unknown', 'reason':'warming up'},
                 {'validity':'invalid', 'reason':'dropout'},
                 {'effective_ns':None}, {'frame_id':'wrong'}, {'source':'vision'})
        for changes in cases:
            with self.subTest(changes=changes):
                p = self.policy()
                self.assertIsNone(p.act(obs(**changes)))
                self.assertTrue(p.fault_reason)
                self.assertIsNone(p.act(obs(1, 1_000_000)))
                p.reset(SESSION)
                self.assertIsNotNone(p.act(obs()))

    def test_stale_effective_time_cadence_and_sequence_gaps_latch(self):
        for bad in (obs(1, 3_000_000, effective_ns=0), obs(1, 10_000_000),
                    obs(2, 1_000_000), obs(0, 1_000_000), obs(1, 0)):
            with self.subTest(bad=bad):
                p = self.policy()
                p.act(obs())
                self.assertIsNone(p.act(bad))
                self.assertTrue(p.fault_reason)
        p = self.policy(max_age_ns=0)
        self.assertIsNone(p.act(obs(0, 1_000_000, effective_ns=0)))

    def test_requires_reset_session_ownership_and_single_joint(self):
        p = ReferencePolicy(ANGLE, POSITION)
        with self.assertRaises(ValidationError):
            p.act(obs())
        p.reset(SESSION)
        with self.assertRaises(ValidationError):
            p.act(replace(obs(), session_id='another'))
        with self.assertRaises(ValidationError):
            p.reset(Session('test','simulation',Topology(joints=('pole','pole2'))))

    def test_invalid_config_and_start_rejection_are_explicit(self):
        for kwargs in ({'start_mode':'manual'}, {'max_age_ns':True}, {'max_age_ns':-1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                ReferencePolicy(ANGLE, POSITION, **kwargs)
        with self.assertRaises(ValidationError):
            ReferencePolicy(POSITION, ANGLE)
        p = self.policy()
        self.assertIsNone(p.act(obs(value=2.5)))
        self.assertTrue(p.fault_reason)
