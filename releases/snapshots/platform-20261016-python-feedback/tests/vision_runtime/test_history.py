import time
import unittest
from cartpole_vision.app import Engine, create_app
from .test_detector import scene


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.client = create_app(self.engine).test_client()

    def test_dashboard_receives_every_processed_frame_between_polls(self):
        start = time.monotonic()
        for seq in range(1, 9):
            self.engine.process(scene(), start + seq / 80, seq)
        state = self.client.get('/api/state?history=1').get_json()
        self.assertIn('history', state, 'full measurement history is missing')
        history = state['history']
        self.assertEqual([r['seq'] for r in history['samples']], list(range(1, 9)))
        self.engine.process(scene(), start + 9 / 80, 9)
        data = self.client.get('/api/state', query_string={
            'history': '1', 'after': 8, 'epoch': history['epoch']}).get_json()['history']
        self.assertEqual([r['seq'] for r in data['samples']], [9])
        self.assertFalse(data['reset'])
        self.assertNotIn('history', self.client.get('/api/state').get_json())

    def test_null_measurements_and_skipped_capture_sequences_are_preserved(self):
        import numpy as np
        now = time.monotonic()
        self.engine.estimator.home_angle = 0
        self.engine.estimator.home_length = 180
        self.engine.process(scene(), now, 1)
        self.engine.process(np.zeros((600, 800, 3), np.uint8), now + .0125, 2)
        self.engine.process(scene(), now + .05, 5)
        data = self.client.get('/api/state?history=1').get_json()
        self.assertIn('history', data, 'full measurement history is missing')
        rows = data['history']['samples']
        self.assertEqual([r['seq'] for r in rows], [1, 2, 5])
        self.assertIsNotNone(rows[0]['theta_rad'])
        self.assertIsNone(rows[1]['theta_rad'])
        self.assertFalse(rows[1]['angle_valid'])

    def test_calibration_reset_clears_history_and_changes_epoch(self):
        now = time.monotonic()
        self.engine.process(scene(), now, 1)
        data = self.client.get('/api/state?history=1').get_json()
        self.assertIn('history', data, 'full measurement history is missing')
        epoch = data['history']['epoch']
        self.assertEqual(self.client.post('/api/reset').status_code, 200)
        new = self.client.get('/api/state', query_string={
            'history': '1', 'epoch': epoch, 'after': 1}).get_json()['history']
        self.assertNotEqual(new['epoch'], epoch)
        self.assertEqual(new['samples'], [])
        self.assertTrue(new['reset'])

    def test_buffer_is_bounded_and_reconnect_returns_retained_measurements(self):
        self.assertTrue(hasattr(self.engine, 'history'), 'measurement buffer missing')
        for seq in range(1, 5001):
            self.engine.history.append({'seq': seq, 't': seq / 80,
                                        'theta_rad': .2, 'angle_valid': True})
        data = self.client.get('/api/state?history=1').get_json()['history']
        self.assertLessEqual(len(data['samples']), 1201)
        self.assertEqual(data['last_seq'], 5000)
        self.assertGreaterEqual(data['samples'][0]['t'], 5000 / 80 - 15)
        retry = self.client.get('/api/state', query_string={
            'history': '1', 'epoch': data['epoch'], 'after': 1}).get_json()['history']
        self.assertTrue(retry['reset'])
        self.assertEqual(retry['last_seq'], 5000)

    def test_bad_history_cursor_is_rejected_and_script_is_served(self):
        self.assertEqual(self.client.get('/api/state?history=1&after=nope').status_code, 400)
        response = self.client.get('/traces.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response.content_type)


if __name__ == '__main__': unittest.main()
