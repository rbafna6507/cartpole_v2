import time
import unittest
from test_detector import scene
from pendulum_vision.app import Engine,create_app

class AppTests(unittest.TestCase):
    def setUp(self):
        self.engine=Engine();self.client=create_app(self.engine).test_client()
    def test_stale_camera_cannot_calibrate(self):
        self.assertEqual(self.client.post('/api/home').status_code,409)
        s=self.client.get('/api/state').get_json()
        self.assertFalse(s['angle_valid'])
    def test_live_calibration_and_reset(self):
        for i in range(26):self.engine.process(scene(),time.monotonic(),i+1)
        response=self.client.post('/api/home')
        self.assertEqual(response.status_code,200,response.get_json())
        self.engine.process(scene(),time.monotonic(),27)
        self.assertTrue(self.client.get('/api/state').get_json()['angle_valid'])
        self.assertEqual(self.client.post('/api/reset').status_code,200)
        self.assertFalse(self.client.get('/api/state').get_json()['angle_valid'])
    def test_malformed_selection_fails_without_server_error(self):
        self.engine.process(scene(),time.monotonic(),1)
        for body in [{},{'x':float('nan'),'y':.4}, {'x':2,'y':.5}, []]:
            self.assertEqual(self.client.post('/api/select',json=body).status_code,400)
    def test_wrong_cart_span_returns_error(self):
        self.engine.process(scene(),time.monotonic(),1)
        r=self.client.post('/api/cart/b',json={'span_mm':'bad'})
        self.assertEqual(r.status_code,400)
    def test_camera_dimensions_change_invalidates_calibration(self):
        import cv2
        self.engine.estimator.home_angle=0;self.engine.estimator.home_length=180
        self.engine.process(scene(),time.monotonic(),1)
        self.engine.process(cv2.resize(scene(),(400,300)),time.monotonic()+.0125,2)
        self.assertIsNone(self.engine.estimator.home_angle)
    def test_disagreeing_cart_template_stays_disabled_during_occlusion(self):
        import numpy as np
        f=scene(); patch=np.random.default_rng(42).integers(40,230,(35,60,3),dtype=np.uint8)
        f[100:135,100:160]=patch
        now=time.monotonic();self.engine.process(f,now,1)
        self.engine.cart.select(f,(100,100,60,35),(320,240))
        moved=scene(pivot=(400,240));moved[100:135,100:160]=patch
        self.engine.process(moved,now+.02,2)
        hidden=np.full_like(f,35);hidden[100:135,100:160]=patch
        r=self.engine.process(hidden,now+.04,3)
        self.assertIsNone(r["cart_pivot_px"])
        self.assertFalse(r["cart_valid"])

    def test_preview_page_and_finite_json(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.engine.process(scene(),time.monotonic(),1)
        self.assertNotIn(b'NaN',self.client.get('/api/state').data)

    def test_measurement_quality_clock_and_latency_are_exposed(self):
        before=time.monotonic()
        self.engine.process(scene(),before,1)
        s=self.client.get('/api/state').get_json()
        self.assertIn('measurement_quality',s)
        self.assertGreaterEqual(s['host_read_to_result_ms'],s['processing_ms'])
        self.assertEqual(s['measurement_quality']['totals']['detected_frames'],1)
        response=self.client.get('/api/clock')
        self.assertEqual(response.status_code,200)
        self.assertLessEqual(before,response.get_json()['monotonic_s'])
        self.assertLessEqual(response.get_json()['monotonic_s'],time.monotonic())
if __name__=='__main__':unittest.main()
