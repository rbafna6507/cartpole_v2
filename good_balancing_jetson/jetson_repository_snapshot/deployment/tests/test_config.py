import json
import math
import tempfile
import unittest
from pathlib import Path

from cartpole_deploy.config import RigConfig
from cartpole_deploy.types import Observation


class ConfigTests(unittest.TestCase):
    def test_effective_length_preserves_pendulum_inertia(self):
        c = RigConfig()
        self.assertAlmostEqual(c.pivot_inertia_kg_m2 /
                               (c.total_pendulum_mass_kg * c.com_m), c.effective_length_m)

    def test_invalid_physics_and_timing_rejected(self):
        for kwargs in ({'arm_length_m': 0}, {'cart_mass_kg': math.nan},
                       {'damping_per_s': -1}, {'policy_dt_s': .0015},
                       {'rail_half_m': .01}, {'encoder_counts': 2.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RigConfig(**kwargs)

    def test_roundtrip_and_unknown_fields(self):
        c = RigConfig(provenance={'assembly_confirmed': False})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'rig.json'
            c.save(p)
            self.assertEqual(RigConfig.load(p).to_dict(), c.to_dict())
            p.write_text(json.dumps({'unrecognized': 1}))
            with self.assertRaises(ValueError):
                RigConfig.load(p)

    def test_observation_flags_and_serialization(self):
        o = Observation(1, 'DISARMED', 0, 0, 0, 0, 0, 0, 3, 0, 0, 'none')
        self.assertTrue(o.encoder_valid)
        self.assertTrue(o.homed)
        self.assertFalse(o.enabled)
        self.assertEqual(o.to_dict()['position_source'], 'commanded_steps')
