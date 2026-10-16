"""Short physical-style serial packets must not wait for a full 512-byte read."""
import importlib.util
import os
import pty
import time
import unittest
from cartpole_sdk.rig.transport import SerialTransport

@unittest.skipUnless(importlib.util.find_spec('serial'), 'hardware extra required')
class SerialPacketTests(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.transport = SerialTransport(os.ttyname(self.slave))
        self.transport._serial.timeout = .2
    def tearDown(self):
        self.transport.close()
        os.close(self.master)
        os.close(self.slave)
    def test_short_packet_is_returned_without_waiting_for_read_capacity(self):
        packet=b'one complete packet\n'
        os.write(self.master,packet)
        began=time.monotonic()
        result=self.transport.read(512)
        elapsed=time.monotonic()-began
        self.assertTrue(result and packet.startswith(result))
        self.assertLess(elapsed,.1,'available serial bytes waited for the fill timeout')
    def test_read_capacity_remains_bounded(self):
        os.write(self.master,b'0123456789')
        self.assertTrue(0 < len(self.transport.read(3)) <= 3)
