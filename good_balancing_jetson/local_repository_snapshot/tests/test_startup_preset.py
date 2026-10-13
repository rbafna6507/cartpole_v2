"""Exercise preset restoration through the real serial parser and TCP transport."""
import binascii
import json
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import cartpole

FW = 'swingup-125mm-60t-v33-teensy41'


class Board:
    def __init__(self, *, firmware=FW, stop_ack=True, reject=None, wrong=None,
                 omit_final=None, enabled=0):
        self.firmware, self.stop_ack = firmware, stop_ack
        self.reject, self.wrong, self.omit_final = reject, wrong, omit_final
        self.enabled = enabled
        self.values = {'pw': 6., 'bal_pw': 8., 'rail': .26, 'k1': -20.83007,
                       'encoder_upright_raw': 2384., 'bal_k4': -2.4471357}
        self.commands, self.changed = [], False
        self.done = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        self.listener.settimeout(3)
        try:
            conn, _ = self.listener.accept()
            with conn:
                conn.settimeout(.02)
                pending = b''
                started = time.monotonic()
                def emit(line):
                    data = line.encode()
                    conn.sendall(b'@' + data + f'*{binascii.crc_hqx(data, 0xffff):04X}\n'.encode())
                while not self.done.is_set():
                    try:
                        data = conn.recv(4096)
                        if not data: break
                        pending += data
                    except socket.timeout:
                        pass
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        cmd = line.decode(); self.commands.append(cmd)
                        parts = cmd.split()
                        if cmd == 'stop' and self.stop_ack: emit('# STOP')
                        elif cmd == 'params':
                            for key, value in self.values.items():
                                if self.changed and key == self.omit_final: continue
                                emit(f'= {key} {value}')
                            emit('# firmware ' + self.firmware)
                        elif cmd == 'enc':
                            emit(f'E 1000 336 336 25 103 0 1 {self.enabled}')
                        elif parts[:1] == ['set']:
                            self.changed = True
                            key, value = parts[1], float(parts[2])
                            if key == self.reject: emit('! rejected parameter'); continue
                            self.values[key] = value + 1 if key == self.wrong else value
                            emit(f'= {key} {self.values[key]}')
                    ms = 1000 + int((time.monotonic() - started) * 1000)
                    emit(f'T {ms} 0 3.1 0 -0.11921 0 0 -1 0 0 25 143')
        except (OSError, TimeoutError):
            pass

    def close(self):
        self.done.set(); self.listener.close(); self.thread.join(4)


class PresetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.json'
        self.preset = {'schema': 1, 'firmware': FW,
                       'settings': {'pw': 4.5, 'bal_pw': 4.},
                       'computed_gains': {'k1': -20.83007},
                       'calibration': {'saved_upright_raw_for_this_rig': 1411}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.preset))

    def connect(self, **kwargs):
        board = Board(**kwargs); self.addCleanup(board.close)
        link = cartpole.Link(f'socket://127.0.0.1:{board.port}',
                             logdir=self.temp.name, reconnect=False, verbose=False)
        self.addCleanup(link.close)
        return board, link

    def apply(self, link):
        self.assertTrue(hasattr(cartpole, 'apply_startup_preset'), 'startup preset restoration missing')
        return cartpole.apply_startup_preset(link, cartpole.load_preset(self.path), timeout=.6)

    def test_restores_gains_without_motion_or_recalibration_and_reports_readback(self):
        board, link = self.connect()
        report = self.apply(link)
        self.assertEqual(board.values['pw'], 4.5)
        self.assertEqual(board.values['bal_pw'], 4.)
        self.assertEqual(board.values['encoder_upright_raw'], 2384.)
        self.assertEqual(report['after']['pw'], 4.5)
        self.assertEqual(report['before']['pw'], 6.)
        self.assertEqual(report['encoder']['enabled'], 0)
        self.assertTrue(all(c.split()[0] in {'stop','ping','rate','params','enc','set'} for c in board.commands))
        self.assertEqual([c for c in board.commands if c.startswith('set ')], ['set pw 4.5', 'set bal_pw 4'])

    def test_invalid_or_calibration_settings_are_rejected_before_sending(self):
        self.assertTrue(hasattr(cartpole, 'load_preset'), 'preset validation missing')
        for key, value in [('pw', float('nan')), ('pw', True), ('pw', '4.5'),
                           ('encoder_upright_raw', 1411), ('pw\n auto', 4.5), ('k1', -20.)]:
            with self.subTest(key=key, value=value):
                self.preset['settings'] = {key: value}; self.save()
                with self.assertRaises(ValueError): cartpole.load_preset(self.path)

    def test_wrong_firmware_or_no_stop_ack_never_changes_parameters(self):
        for kwargs in [{'firmware':'different-firmware'}, {'stop_ack':False}, {'enabled':1}]:
            with self.subTest(kwargs=kwargs):
                board, link = self.connect(**kwargs)
                with self.assertRaises(RuntimeError): self.apply(link)
                self.assertFalse(any(c.startswith('set ') for c in board.commands))

    def test_rejected_or_wrong_readback_fails_and_stops(self):
        for kwargs in [{'reject':'pw'}, {'wrong':'pw'}, {'omit_final':'pw'}]:
            with self.subTest(kwargs=kwargs):
                board, link = self.connect(**kwargs)
                with self.assertRaises(RuntimeError): self.apply(link)
                time.sleep(.04)
                self.assertIn('stop', board.commands)

    def test_wrong_computed_gains_are_not_reported_as_success(self):
        board, link = self.connect(); board.values['k1'] = -99
        with self.assertRaisesRegex(RuntimeError, 'k1'): self.apply(link)

    def test_cli_applies_preset_before_console_and_exits_stopped(self):
        board = Board(); self.addCleanup(board.close)
        result = subprocess.run([sys.executable, cartpole.__file__, '--host', '127.0.0.1',
                                 '--tcp-port', str(board.port), '--text', '--preset', str(self.path),
                                 '--logdir', self.temp.name], input='quit\n', text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Preset verified', result.stdout)
        self.assertEqual(board.values['pw'], 4.5)
        self.assertEqual([c for c in board.commands if c != 'ping'][-1], 'stop')
        reports = list(Path(self.temp.name).glob('*_preset.json'))
        self.assertEqual(len(reports), 1)
        self.assertEqual(json.loads(reports[0].read_text())['after']['bal_pw'], 4.)

    def test_default_preset_is_loaded_relative_to_saved_console_from_any_cwd(self):
        root = Path(self.temp.name)
        snapshot = root / 'local_repository_snapshot'; snapshot.mkdir()
        for name in ('cartpole.py', 'angle_plot.py', 'console_preset.py'):
            shutil.copy(Path(cartpole.__file__).parent / name, snapshot / name)
        board = Board(); self.addCleanup(board.close)
        result = subprocess.run([sys.executable, str(snapshot / 'cartpole.py'),
                                 '--host', '127.0.0.1', '--tcp-port', str(board.port),
                                 '--text', '--logdir', str(root / 'logs')],
                                cwd='/', input='quit\n', text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Preset verified', result.stdout)
        self.assertEqual(board.values['pw'], 4.5)
        self.assertEqual(board.values['bal_pw'], 4.)

    def test_missing_preset_does_not_open_a_connection(self):
        result = subprocess.run([sys.executable, cartpole.__file__, '--preset',
                                 str(Path(self.temp.name) / 'missing.json'),
                                 '--port', '/does/not/exist'],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('cannot load preset', result.stderr)
        self.assertNotIn('SerialException', result.stderr)


if __name__ == '__main__': unittest.main()
