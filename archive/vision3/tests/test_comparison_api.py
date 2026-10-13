import unittest
from pendulum_vision.app import Engine,create_app
class ComparisonApiTests(unittest.TestCase):
    def test_encoder_is_served_without_camera_and_cursor_does_not_repeat(self):
        e=Engine();client=create_app(e).test_client()
        self.assertTrue(hasattr(e,'comparison'),'Engine must own independent sensor comparison')
        import time
        t=time.monotonic()
        e.comparison.encoder(dict(v=1,session='test',seq=1,board_ms=0,host_t=t,theta=.2,theta_dot=0.,upright=3475,generation=0,valid=True,health={'status':'ok','age_s':0.}),now=t)
        d=client.get('/api/state?history=1').get_json()['comparison']
        self.assertEqual(d['encoder']['samples'][0]['theta_rad'],.2)
        again=client.get('/api/state?history=1&comparison_after='+str(d['last_seq'])+'&comparison_epoch='+d['epoch']).get_json()['comparison']
        self.assertEqual(again['encoder']['samples'],[])
        self.assertEqual(client.get('/api/state?history=1&comparison_after=oops').status_code,400)
    def test_reset_starts_new_comparison_epoch(self):
        e=Engine();client=create_app(e).test_client()
        self.assertTrue(hasattr(e,'comparison'))
        old=e.comparison.epoch
        client.post('/api/reset')
        self.assertNotEqual(old,e.comparison.epoch)


class ComparisonSettingsTests(unittest.TestCase):
    def test_direction_and_delay_are_explicit_validated_display_settings(self):
        e=Engine();client=create_app(e).test_client()
        old=e.comparison.epoch
        response=client.post('/api/comparison',json={'encoder_sign':-1,'vision_delay_ms':25})
        self.assertEqual(response.status_code,200)
        self.assertEqual(e.comparison.encoder_sign,-1)
        self.assertEqual(e.comparison.vision_delay,.025)
        self.assertNotEqual(e.comparison.epoch,old)
        for body in ({'encoder_sign':0,'vision_delay_ms':0},{'encoder_sign':1,'vision_delay_ms':float('nan')},[]):
            self.assertEqual(client.post('/api/comparison',json=body).status_code,400)
