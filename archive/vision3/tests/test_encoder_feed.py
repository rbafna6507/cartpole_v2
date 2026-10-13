import json, math, socket, sys, time, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'console'))
from vision_telemetry import Publisher
from pendulum_vision.encoder_feed import Comparison

class FeedTests(unittest.TestCase):
    def packet(self,i,t,theta=.2,session='one',upright=3475):
        return dict(v=1,session=session,seq=i,board_ms=i*10,host_t=t,theta=theta,theta_dot=0.,upright=upright,generation=0,valid=True,health={'status':'ok','age_s':0.})
    def test_real_udp_publisher_and_no_receiver(self):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',0));s.settimeout(1)
        p=Publisher(s.getsockname()[1])
        p.publish(100,.2,.3,3475,now=20)
        data=json.loads(s.recv(4096));self.assertEqual(data['theta'],.2);self.assertEqual(data['host_t'],20)
        s.close()
        for _ in range(100):p.publish(110,.2,.3,3475,now=20.01)
        p.close()
    def test_encoder_history_advances_without_camera_and_invalid_packets_rejected(self):
        c=Comparison()
        for i in range(50):self.assertTrue(c.encoder(self.packet(i+1,100+i*.01),now=100+i*.01))
        result=c.snapshot(100.49)
        self.assertEqual(len(result['encoder']['samples']),50)
        self.assertEqual(result['status']['source'],'encoder only')
        self.assertGreater(result['status']['encoder_hz'],90)
        self.assertFalse(c.encoder(self.packet(10,100.5),now=100.5))
        self.assertFalse(c.encoder({**self.packet(60,100.6),'theta':float('nan')},now=100.6))
    def test_reference_and_session_changes_reset_filter(self):
        c=Comparison();c.encoder(self.packet(1,10,1.5),now=10)
        old=c.snapshot(10)['epoch']
        c.encoder(self.packet(2,10.01,-.2,upright=3500),now=10.01)
        s=c.snapshot(10.01);self.assertNotEqual(old,s['epoch'])
        self.assertAlmostEqual(s['status']['theta'],-.2)
        self.assertEqual(len(s['encoder']['samples']),1)
    def test_vision_is_optional_and_fusion_logs_both_sources(self):
        c=Comparison()
        for i in range(40):
            t=100+i*.01
            c.encoder(self.packet(i+1,t),now=t)
            c.vision(dict(t=t,theta_rad=.2,angle_valid=True,confidence=.9),now=t+.01)
        s=c.snapshot(100.4)
        self.assertEqual(s['status']['source'],'both')
        self.assertAlmostEqual(s['status']['disagreement_deg'],0,delta=.01)
        self.assertLess(len(c.snapshot(100.4,after=s['last_seq'],epoch=s['epoch'])['encoder']['samples']),1)
    def test_stale_and_future_datagrams_rejected(self):
        c=Comparison()
        self.assertFalse(c.encoder(self.packet(1,10),now=11))
        self.assertFalse(c.encoder(self.packet(1,11),now=10))

    def test_health_is_required_and_expires_even_if_telemetry_continues(self):
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0));udp.settimeout(1)
        p=Publisher(udp.getsockname()[1])
        p.publish(100,.2,0.,3475,now=10)
        self.assertFalse(json.loads(udp.recv(4096))['valid'])
        p.health(100,True,32,0,now=10)
        p.publish(110,.2,0.,3475,now=10.01)
        self.assertTrue(json.loads(udp.recv(4096))['valid'])
        p.publish(500,.2,0.,3475,now=10.4)
        self.assertFalse(json.loads(udp.recv(4096))['valid'])
        p.health(500,False,32,1,now=10.4)
        p.publish(510,.2,0.,3475,now=10.41)
        self.assertFalse(json.loads(udp.recv(4096))['valid'])
        p.close();udp.close()


    def test_health_age_advances_when_console_stops_and_backlogged_health_is_rejected(self):
        c=Comparison();c.encoder(self.packet(1,10),now=10)
        h=c.snapshot(10.4)['status']['encoder_health']
        self.assertEqual(h['status'],'stale')
        self.assertAlmostEqual(h['age_s'],.4)
        packet=self.packet(2,10.1)
        packet['health']={'status':'ok','age_s':.2}
        self.assertFalse(c.encoder(packet,now=10.2))
