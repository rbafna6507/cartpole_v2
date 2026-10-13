"""Use the installed entry point from outside the repository."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([str(Path(sys.executable).with_name('cartpole-v2')), *map(str, args)],
                              cwd='/', capture_output=True, text=True, timeout=10)

    def test_import_inspect_and_replay_are_available_outside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording = Path(tmp)/'vision.jsonl'
            trace = Path(tmp)/'actions.jsonl'
            result = self.run_cli('import-vision', FIXTURES/'vision-real.jsonl', recording,
                                 '--session-id', 'demo', '--frame-id', 'cal-1')
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli('inspect', recording)
            self.assertEqual(result.returncode, 0, result.stderr)
            info = json.loads(result.stdout)
            self.assertEqual(info['session_id'], 'demo')
            self.assertEqual(info['observations'], 4)
            self.assertEqual(info['sources'], ['vision'])
            result = self.run_cli('replay', recording, trace, '--frame-id', 'cal-1')
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in trace.read_text().splitlines()]
            self.assertEqual(rows[0]['mode'], 'open_loop_replay')
            self.assertTrue(any(row.get('status') == 'requested' for row in rows))
            before = trace.read_bytes()
            result = self.run_cli('replay', recording, trace, '--frame-id', 'cal-1')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(trace.read_bytes(), before)

    def test_console_import_preserves_unknown_health_and_creates_segment_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)/'console'
            result = self.run_cli('import-console', FIXTURES/'console-real.csv', dest,
                                 '--session-id', 'baseline', '--frame-id', 'encoder-home-1')
            self.assertEqual(result.returncode, 0, result.stderr)
            files = list(dest.glob('*.jsonl'))
            self.assertEqual(len(files), 1)
            result = self.run_cli('inspect', files[0])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['validity_counts']['valid'], 0)
            result = self.run_cli('import-console', FIXTURES/'console-real.csv', dest,
                                 '--session-id', 'baseline', '--frame-id', 'encoder-home-1')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(dest.glob('*.jsonl')), files)

    def test_invalid_recording_errors_cleanly_without_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp)/'bad.jsonl', Path(tmp)/'trace.jsonl'
            source.write_text('{"version":99}\n')
            result = self.run_cli('replay', source, target, '--frame-id', 'cal')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('error:', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(target.exists())

    def test_example_script_runs_a_user_editable_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            recording, trace = Path(tmp)/'vision.jsonl', Path(tmp)/'trace.jsonl'
            result = self.run_cli('import-vision', FIXTURES/'vision-real.jsonl', recording,
                                 '--session-id', 'demo', '--frame-id', 'cal-1')
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([sys.executable, str(ROOT/'examples'/'replay_policy.py'),
                str(recording), str(trace), '--frame-id', 'cal-1'], cwd='/',
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(trace.exists())
