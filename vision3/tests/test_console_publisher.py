import binascii, importlib.util, json, os, socket, sys, tempfile, time, unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'console'
sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('fusion_console',root/'cartpole.py')
console=importlib.util.module_from_spec(spec);spec.loader.exec_module(console)
def frame(s):
    b=s.encode();return b'@'+b+b'*'+f'{binascii.crc_hqx(b,0xffff):04X}'.encode()+b'\n'
class ConsolePublisherTests(unittest.TestCase):
    def test_checked_serial_telemetry_reaches_udp_and_home_resets_generation(self):
        import inspect
        self.assertIn('vision_telemetry_port',inspect.signature(console.Link).parameters,'Link must expose publishing endpoint')
        master,slave=os.openpty()
        udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(('127.0.0.1',0));udp.settimeout(1)
        with tempfile.TemporaryDirectory() as directory:
            link=console.Link(os.ttyname(slave),logdir=directory,verbose=False,vision_telemetry_port=udp.getsockname()[1])
            try:
                os.write(master,frame('= encoder_upright_raw 3475')+frame('E 100 2000 1000 100 32 0 1 0')+frame('T 100 0 0.2 0.3 0 0 0 0 0 0 100 1000'))
                p=json.loads(udp.recv(4096));self.assertTrue(p['valid']);self.assertAlmostEqual(p['theta'],.2);self.assertEqual(p['upright'],3475)
                link.send('home')
                os.write(master,frame('T 110 0 0.2 0.3 0 0 0 0 0 0 100 1000'))
                later=json.loads(udp.recv(4096));self.assertFalse(later['valid']);self.assertGreater(later['generation'],p['generation'])
                os.write(master,b'@T corrupted*0000\n')
                udp.settimeout(.1)
                with self.assertRaises(socket.timeout):udp.recv(4096)
            finally:link.close()
        udp.close();os.close(master);os.close(slave)
