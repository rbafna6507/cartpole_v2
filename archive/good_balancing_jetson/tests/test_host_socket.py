"""Run from bundle root: python3 -m unittest discover -s tests"""
import socket
import threading
import unittest
from unittest.mock import patch
import cartpole

class HostTransportTest(unittest.TestCase):
    def test_socket_transport_round_trip(self):
        listener=socket.socket()
        listener.bind(('127.0.0.1',0));listener.listen(1)
        received=[]
        def peer():
            conn,_=listener.accept()
            with conn:
                conn.settimeout(2)
                received.append(conn.recv(32))
                conn.sendall(b'@STOP*1234\n')
        thread=threading.Thread(target=peer);thread.start()
        link=cartpole.Link.__new__(cartpole.Link)
        link.port_name=f'socket://127.0.0.1:{listener.getsockname()[1]}'
        link.baud=115200
        port=link._open_port()
        try:
            port.write(b'stop\n')
            self.assertEqual(port.read(11),b'@STOP*1234\n')
        finally:
            port.close();thread.join(3);listener.close()
        self.assertEqual(received,[b'stop\n'])

    def test_usb_arguments_unchanged(self):
        link=cartpole.Link.__new__(cartpole.Link)
        link.port_name='/dev/cu.test';link.baud=115200
        with patch.object(cartpole.serial,'Serial') as constructor:
            link._open_port()
            constructor.assert_called_once_with('/dev/cu.test',115200,timeout=.1,write_timeout=.5,exclusive=True)
