"""Exercise the portable entry point against the saved preset and a fake board."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_startup_preset import Board

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_relocated_launcher_restores_full_saved_preset_and_preserves_reference(self):
        self.assertTrue((ROOT / 'console/launch.py').is_file(), 'portable launcher is missing')
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / 'bundle with spaces'
            shutil.copytree(ROOT / 'console', bundle / 'console')
            shutil.copy2(ROOT / 'settings.json', bundle / 'settings.json')
            preset = json.loads((bundle / 'settings.json').read_text())
            board = Board()
            self.addCleanup(board.close)
            board.values = {**preset['settings'], **preset['computed_gains'],
                            'encoder_upright_raw': 3475.0}
            board.values['pw'] = 6.0
            board.values['bal_pw'] = 8.0
            env = os.environ.copy()
            env.pop('PYTHONPATH', None)
            result = subprocess.run(
                [sys.executable, str(bundle / 'console/launch.py'), '--host=127.0.0.1',
                 '--tcp-port', str(board.port), '--rate', '100',
                 '--vision-telemetry-port', '0', '--logdir', str(Path(tmp) / 'logs')],
                cwd='/', input='quit\n', text=True, capture_output=True, timeout=15, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('(33 settings)', result.stdout)
            self.assertAlmostEqual(board.values['pw'], 4.5)
            self.assertAlmostEqual(board.values['bal_pw'], 4.0)
            self.assertEqual(board.values['encoder_upright_raw'], 3475.0)
            self.assertFalse(set(c.split()[0] for c in board.commands) &
                             {'auto', 'bal', 'manual', 'v', 'on', 'home', 'upright', 'zero'})
            self.assertEqual([c for c in board.commands if c not in ('ping', 'enc')][-1], 'stop')
            reports = list((Path(tmp) / 'logs').glob('*_preset.json'))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertEqual(report['restored_settings'], preset['settings'])
            self.assertEqual(report['encoder']['enabled'], 0)

    def test_help_does_not_need_a_serial_device_or_preset(self):
        self.assertTrue((ROOT / 'console/launch.py').is_file(), 'portable launcher is missing')
        result = subprocess.run([sys.executable, str(ROOT / 'console/launch.py'), '--help'],
                                cwd='/', text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--preset', result.stdout)


if __name__ == '__main__':
    unittest.main()
