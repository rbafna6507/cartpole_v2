"""Keep boot parameters and simulator aligned with the selected hardware preset."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TunedDefaultsTest(unittest.TestCase):
    def test_boot_and_simulator_match_full_span_preset(self):
        preset = json.loads((ROOT / 'analysis/v33_span_tuning/recommended_settings.json').read_text())
        expected = {**preset['fixed_limits'], **preset['gains'],
                    'rail': preset['virtual_rail_half_m'], 'bal_pw': 8,
                    'amax_m': .5, 'jmax_m': 10, 'spin_resume_rad_s': 10}
        assertions = '\n'.join(
            f'assert(std::fabs(p.{key} - ({value})) < 1e-5);'
            for key, value in expected.items())
        source = f'''#include "{ROOT}/swingup/swing_controller.h"
#include <cassert>
#include <cmath>
int main() {{ swing_control::Parameters p; {assertions} }}
'''
        with tempfile.TemporaryDirectory() as folder:
            cpp = Path(folder) / 'defaults.cpp'
            cpp.write_text(source)
            binary = Path(folder) / 'defaults'
            subprocess.run(['clang++', '-std=c++11', str(cpp), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
        js = subprocess.check_output(['node', '-e',
            "console.log(JSON.stringify(require('./simulator175/engine.js').defaults))"], cwd=ROOT, text=True)
        actual = json.loads(js)
        for key, value in expected.items():
            if key not in ('amax_m', 'jmax_m'):
                self.assertAlmostEqual(actual[key], value, places=5, msg=key)

if __name__ == '__main__':
    unittest.main()
