"""Wire-equivalence checks for the standard-library CCITT CRC fast path."""
import random
import pytest
from cartpole_sdk.rig.protocol import crc16,encode,decode,ProtocolError


def bitwise_ccitt(data):
    """Independent original wire algorithm; retain as an executable oracle."""
    crc=0xffff
    for byte in data:
        crc^=byte<<8
        for _ in range(8):
            crc=((crc<<1)^(0x1021 if crc&0x8000 else 0))&0xffff
    return crc


def test_crc_exhaustive_empty_one_and_two_byte_inputs():
    assert crc16(b'')==0xffff
    assert crc16(b'123456789')==0x29b1
    for value in range(256):
        data=bytes([value]);assert crc16(data)==bitwise_ccitt(data)
    for value in range(65536):
        data=value.to_bytes(2,'big');assert crc16(data)==bitwise_ccitt(data)


def test_crc_seeded_full_length_binary_inputs():
    rng=random.Random(20261016)
    for length in range(256):
        for _ in range(20):
            data=rng.randbytes(length)
            assert crc16(data)==bitwise_ccitt(data)
    for data in (bytes(range(256)),bytes(255),bytes([255])*255):
        assert crc16(data)==bitwise_ccitt(data)


def test_encoder_wire_bytes_and_decoder_crc_rejections_match_original():
    rng=random.Random(16330)
    alphabet=bytes(value for value in range(32,127) if value not in (ord('@'),ord('*')))
    for length in range(1,249):
        body=bytes(rng.choice(alphabet) for _ in range(length))
        frame=b'@'+body+f'*{bitwise_ccitt(body):04X}\n'.encode('ascii')
        assert encode(body.decode('ascii'))==frame
        assert decode(frame)==body.decode('ascii')
        damaged=b'@'+body+f'*{bitwise_ccitt(body)^1:04X}\n'.encode('ascii')
        with pytest.raises(ProtocolError,match='CRC'):decode(damaged)
