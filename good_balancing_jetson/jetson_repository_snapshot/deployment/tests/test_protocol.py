import unittest

from cartpole_deploy.protocol import (
    FrameDecoder, ProtocolError, crc16, encode_frame, decode_frame,
    parse_state, parse_info,
)


class ProtocolTests(unittest.TestCase):
    def test_ccitt_known_vector_and_roundtrip(self):
        self.assertEqual(crc16(b'123456789'), 0x29B1)
        frame = encode_frame('D1 state')
        self.assertEqual(decode_frame(frame), 'D1 state')

    def test_bad_crc_and_noncanonical_frames_rejected(self):
        for frame in [b'@D1 state*0000\n', b'D1 state\n', b'@D1 state*12345\n', b'@D1 state*ZZZZ\n', b'@D1 state*1234\r\n']:
            with self.subTest(frame=frame), self.assertRaises(ProtocolError):
                decode_frame(frame)
        for payload in ['D1 state\n', 'D1 *state', 'D1 @state', 'é', 'x' * 250]:
            with self.subTest(payload=payload), self.assertRaises(ProtocolError):
                encode_frame(payload)

    def test_fragmented_and_batched_frames(self):
        decoder = FrameDecoder()
        frames = encode_frame('D1 state') + encode_frame('D1 info')
        decoded = []
        for byte in frames:
            decoded.extend(decoder.feed(bytes([byte])))
        self.assertEqual(decoded, ['D1 state', 'D1 info'])

    def test_oversize_discard_is_bounded_and_recovers(self):
        decoder = FrameDecoder()
        with self.assertRaises(ProtocolError):
            decoder.feed(b'x' * 10000)
        self.assertLessEqual(decoder.buffer_size, 256)
        self.assertEqual(decoder.feed(b'garbage\n' + encode_frame('D1 info')), ['D1 info'])

    def test_state_exact_shape_finite_ranges(self):
        payload = 'D1 S 4294967295 ARMED 0.2 -1 0.01 0.02 0.03 4095 7 9 11 none'
        state = parse_state(payload)
        self.assertEqual(state.time_us, 4294967295)
        self.assertEqual(state.position_source, 'commanded_steps')
        self.assertTrue(state.homed)
        for bad in [payload + ' extra', payload.replace('ARMED', 'BOGUS'), payload.replace('0.2', 'nan'), payload.replace('4095', '4096'), payload.replace('4294967295', '-1'), payload.replace(' 7 ', ' 8 ')]:
            with self.subTest(bad=bad), self.assertRaises(ProtocolError):
                parse_state(bad)

    def test_info_exact_version_and_truthful_capabilities(self):
        info = parse_info('D1 I 1 1000 500 60 26666.666667 0.15 0.25 2 20 encoder')
        self.assertEqual(info['control_hz'], 1000)
        self.assertFalse(info['imu'])
        self.assertEqual(info['position_source'], 'commanded_steps')
        with self.assertRaises(ProtocolError):
            parse_info('D1 I 2 1000 500 60 26666.666667 0.15 0.25 2 20 encoder')


if __name__ == '__main__':
    unittest.main()
