"""Timing evidence stays in its measured clock domain and preserves I/O behavior."""
import importlib
import json
from types import SimpleNamespace

import pytest

from cartpole_sdk.rig.protocol import UINT32, encode


def api():
    return importlib.import_module('cartpole_sdk.identification.timing_capture')


class Clock:
    def __init__(self, now=1_000):
        self.now = now

    def __call__(self):
        return self.now


class DelayedTransport:
    def __init__(self, clock, *, written=None, error=None, chunks=()):
        self.clock, self.written, self.error = clock, written, error
        self.chunks = iter(chunks)
        self.closed = False
        self.output = bytearray()

    def write(self, data):
        self.clock.now += 40
        if self.error:
            raise self.error
        count = len(data) if self.written is None else self.written
        self.output.extend(data[:count])
        return count

    def read(self, size):
        self.clock.now += 20
        chunk = next(self.chunks)
        assert len(chunk) <= size
        return chunk

    def close(self):
        self.closed = True


def collector():
    rows = []
    return rows, lambda kind, **fields: rows.append(dict(type=kind, **fields))


def state(at, tick, seq=0, *, sid=7, us=None, unwrapped=True):
    values = dict(sid=sid, received_ns=at, tick=tick & UINT32,
                  us=(tick * 1_000 if us is None else us) & UINT32, last_seq=seq)
    if unwrapped:
        values.update(unwrapped_tick=tick, unwrapped_us=tick * 1_000 if us is None else us)
    return dict(type='state', state=values)


def write_rows(seq, start, end, *, sid=7, write_id=None, complete=True):
    identity = dict(write_id=seq if write_id is None else write_id,
                    command=dict(verb='A', sid=sid, sequence=seq))
    return [dict(type='timing_transport_write_start', host_start_ns=start,
                 bytes_requested=30, **identity),
            dict(type='timing_transport_write_end', host_start_ns=start, host_end_ns=end,
                 duration_ns=end-start, bytes_requested=30,
                 bytes_written=30 if complete else 5, complete=complete, **identity)]


def test_transport_records_actual_write_interval_and_bytes_without_payload():
    clock = Clock()
    rows, record = collector()
    inner = DelayedTransport(clock)
    wrapped = api().TimingTransport(inner, record, clock_ns=clock)
    packet = encode('V2 A 7 4 100 20 0.125')
    assert wrapped.write(packet) == len(packet)
    assert bytes(inner.output) == packet
    assert [r['type'] for r in rows] == ['timing_transport_write_start', 'timing_transport_write_end']
    assert rows[0]['host_start_ns'] == 1_000
    assert rows[1]['host_end_ns'] == 1_040
    assert rows[1]['duration_ns'] == 40
    assert rows[1]['bytes_written'] == len(packet)
    assert rows[1]['complete'] is True
    assert rows[1]['command'] == dict(verb='A', sid=7, sequence=4)
    assert '0.125' not in json.dumps(rows)
    wrapped.close()
    assert inner.closed


def test_transport_preserves_short_write_and_exception_evidence():
    clock = Clock()
    rows, record = collector()
    wrapped = api().TimingTransport(DelayedTransport(clock, written=3), record, clock_ns=clock)
    packet = encode('V2 STOP 7')
    assert wrapped.write(packet) == 3
    assert rows[-1]['bytes_written'] == 3
    assert rows[-1]['complete'] is False
    failure = OSError('private transport detail')
    failure.characters_written = 2
    wrapped = api().TimingTransport(DelayedTransport(clock, error=failure), record, clock_ns=clock)
    with pytest.raises(OSError) as caught:
        wrapped.write(packet)
    assert caught.value is failure
    assert rows[-1]['error_type'] == 'OSError'
    assert rows[-1]['bytes_written'] == 2
    assert rows[-1]['complete'] is False
    assert 'private transport detail' not in json.dumps(rows)


def test_empty_reads_are_quiet_and_data_reads_record_no_content():
    clock = Clock()
    rows, record = collector()
    wrapped = api().TimingTransport(DelayedTransport(clock, chunks=[b'', b'private\n']), record, clock_ns=clock)
    assert wrapped.read(512) == b''
    assert not rows
    assert wrapped.read(512) == b'private\n'
    assert rows == [dict(type='timing_transport_read', host_start_ns=1_020,
                         host_end_ns=1_040, duration_ns=20, byte_count=8)]


@pytest.mark.parametrize('packet', [b'password=secret\n', encode('V2 A 7 4 100 20 secret'),
    encode('V2 A 7 4 100 20 nan'), encode('V2 A 7 4 100 20 0') + b'private\n',
    encode('V2 UNKNOWN 7 secret'), b'@V2 A 7 4 100 20 0*0000\n'])
def test_only_exact_known_crc_valid_commands_produce_metadata(packet):
    clock = Clock()
    rows, record = collector()
    wrapped = api().TimingTransport(DelayedTransport(clock), record, clock_ns=clock)
    assert wrapped.write(packet) == len(packet)
    assert all(r.get('command') is None for r in rows)
    assert 'secret' not in json.dumps(rows)


def test_timed_policy_preserves_return_and_optional_capabilities():
    clock = Clock()
    rows, record = collector()

    class Policy:
        mode = 'measuring'
        def reset(self, session):
            self.session = session
        def validate_start(self, observation):
            if observation.sequence < 1:
                raise ValueError('sequence')
        def act(self, observation):
            self.mode = 'ready'
            clock.now += 70
            return observation

    policy = Policy()
    wrapped = api().TimedPolicy(policy, record, clock_ns=clock)
    wrapped.reset('session')
    observation = SimpleNamespace(sequence=9)
    wrapped.validate_start(observation)
    assert wrapped.act(observation) is observation
    assert wrapped.mode == 'ready'
    assert policy.session == 'session'
    assert rows[-1]['duration_ns'] == 70
    assert rows[-1]['observation_sequence'] == 9
    assert rows[-1]['host_start_ns'] == 1_000
    assert rows[-1]['host_end_ns'] == 1_070
    bare = api().TimedPolicy(SimpleNamespace(act=lambda o: None), record, clock_ns=clock)
    assert not hasattr(bare, 'reset')
    assert not hasattr(bare, 'validate_start')
    assert not hasattr(bare, 'timing_diagnostics')


def test_policy_exception_and_recorder_failure_do_not_change_policy_result():
    clock = Clock()
    rows, record = collector()
    failure = ValueError('private policy detail')
    def act(observation):
        clock.now += 10
        raise failure
    wrapped = api().TimedPolicy(SimpleNamespace(act=act), record, clock_ns=clock)
    with pytest.raises(ValueError) as caught:
        wrapped.act(SimpleNamespace(sequence=1))
    assert caught.value is failure
    assert rows[-1]['error_type'] == 'ValueError'
    assert rows[-1]['duration_ns'] == 10
    assert 'private policy detail' not in json.dumps(rows)
    def broken_record(*args, **kwargs):
        raise RuntimeError('sink unavailable')
    wrapped = api().TimedPolicy(SimpleNamespace(act=lambda o: 12), broken_record, clock_ns=clock)
    assert wrapped.act(None) == 12


def test_summary_uses_state_receipts_and_board_gaps_in_separate_units():
    records = [state(1_000, 1), state(1_100, 2), state(1_400, 5), state(1_600, 7),
               *write_rows(1, 1_000, 1_040),
               dict(type='timing_policy_end', host_start_ns=1_000, host_end_ns=1_080, duration_ns=80)]
    report = api().summarize_timing(iter(records))
    assert report['state_receipt_interval_ns'] == dict(count=3, p50=200., p95=290., p99=298., max=300.)
    assert report['board_tick_gap']['p50'] == 2
    assert report['board_us_gap']['max'] == 3_000
    assert report['command_write_duration_ns']['p50'] == 40
    assert report['policy_duration_ns']['p95'] == 80
    json.dumps(report, allow_nan=False)


def test_exact_sequence_receipt_bounds_distinguish_unobserved_from_missed():
    records = [state(90, 1), *write_rows(1, 100, 110), *write_rows(2, 120, 130),
               state(170, 2, seq=2), *write_rows(3, 180, 190)]
    ack = api().summarize_timing(records)['acknowledgements']
    assert ack['written_actions'] == 3
    assert ack['observed_sequences'] == 1
    assert ack['unobserved_sequences'] == 2
    assert ack['telemetry_skipped_sequences'] == 1
    assert ack['right_censored_sequences'] == 1
    assert ack['missed_commands'] is None
    observed = [s for s in ack['samples'] if s['status'] == 'observed'][0]
    assert observed['sequence'] == 2
    assert observed['first_seen_received_ns'] == 170
    assert observed['receipt_elapsed_lower_ns'] == 40
    assert observed['receipt_elapsed_upper_ns'] == 50
    assert 'receipt' in ack['basis']
    assert 'physical' in ack['limitations']


def test_receipt_during_write_is_valid_and_cannot_have_negative_bound():
    records = write_rows(1, 100, 150)
    records.insert(1, state(130, 1, seq=1))
    sample = api().summarize_timing(records)['acknowledgements']['samples'][0]
    assert sample['status'] == 'observed'
    assert sample['receipt_elapsed_lower_ns'] == 0
    assert sample['receipt_elapsed_upper_ns'] == 30


@pytest.mark.parametrize('boundary', [dict(type='session', session=dict(session_id='7', clock_id='teensy:7')),
    dict(type='timing_transport_write_start', write_id=8, host_start_ns=150,
         command=dict(verb='ARM', sid=7), bytes_requested=20)])
def test_session_and_lease_boundaries_do_not_reuse_acknowledgements(boundary):
    records = [*write_rows(1, 100, 110), boundary,
               *write_rows(1, 200, 210, write_id=9), state(240, 2, seq=1)]
    ack = api().summarize_timing(records)['acknowledgements']
    assert ack['observed_sequences'] == 1
    assert ack['right_censored_sequences'] == 1
    assert ack['samples'][0]['status'] == 'right_censored'
    assert ack['samples'][1]['receipt_elapsed_lower_ns'] == 30


def test_action_sequence_wrap_is_a_boundary_not_an_inferred_acknowledgement():
    records = [*write_rows(UINT32, 100, 110), *write_rows(1, 200, 210), state(240, 2, seq=1)]
    report = api().summarize_timing(records)
    assert report['counts']['sequence_boundaries'] == 1
    assert report['acknowledgements']['observed_sequences'] == 1
    assert report['acknowledgements']['right_censored_sequences'] == 1


def test_board_counter_wrap_is_unwrapped_but_reset_does_not_create_huge_gap():
    records = [state(100, UINT32-1, us=UINT32-999, unwrapped=False),
               state(200, 2, us=3_000, unwrapped=False),
               state(300, 1, us=1_000, unwrapped=False)]
    report = api().summarize_timing(records)
    assert report['board_tick_gap']['count'] == 1
    assert report['board_tick_gap']['max'] == 4
    assert report['board_us_gap']['max'] == 4_000
    assert report['counts']['board_counter_boundaries'] == 1


def test_invalid_negative_or_nonfinite_timestamps_are_counted_without_bogus_stats():
    records = [state(-1, 1), state(100, 2), state(90, 3), state(120, 4),
               *write_rows(1, -100, -90), *write_rows(2, 200, 190),
               dict(type='timing_policy_end', host_start_ns=1, host_end_ns=float('inf'))]
    report = api().summarize_timing(records)
    assert report['counts']['invalid_timing_records'] >= 4
    assert report['command_write_duration_ns']['count'] == 0
    assert report['policy_duration_ns']['count'] == 0
    assert report['acknowledgements']['written_actions'] == 0
    assert report['state_receipt_interval_ns']['max'] == 30
    json.dumps(report, allow_nan=False)


def test_partial_writes_are_reported_but_not_counted_as_acknowledgeable_actions():
    report = api().summarize_timing([*write_rows(1, 100, 110, complete=False), state(150, 1, seq=1)])
    assert report['counts']['partial_writes'] == 1
    assert report['acknowledgements']['written_actions'] == 0
    assert report['command_write_duration_ns']['count'] == 1


def test_empty_summary_is_finite_and_explicit_about_absent_evidence():
    report = api().summarize_timing([])
    assert report['state_receipt_interval_ns'] == dict(count=0, p50=None, p95=None, p99=None, max=None)
    assert report['acknowledgements']['written_actions'] == 0
    json.dumps(report, allow_nan=False)


def test_read_exception_keeps_original_error_and_timing_evidence():
    clock = Clock()
    rows, record = collector()
    failure = OSError('private read detail')
    def read(size):
        clock.now += 15
        raise failure
    wrapped = api().TimingTransport(SimpleNamespace(read=read), record, clock_ns=clock)
    with pytest.raises(OSError) as caught:
        wrapped.read(512)
    assert caught.value is failure
    assert rows[-1]['error_type'] == 'OSError'
    assert rows[-1]['duration_ns'] == 15
    assert 'private read detail' not in json.dumps(rows)


def test_transport_sink_failure_does_not_prevent_write_or_mask_its_error():
    clock = Clock()
    def broken_record(*args, **kwargs):
        raise RuntimeError('sink failed')
    inner = DelayedTransport(clock)
    wrapped = api().TimingTransport(inner, broken_record, clock_ns=clock)
    assert wrapped.write(b'abc') == 3
    assert bytes(inner.output) == b'abc'
    assert wrapped.record_errors == 2
    failure = OSError('transport failure')
    inner.error = failure
    with pytest.raises(OSError) as caught:
        wrapped.write(b'def')
    assert caught.value is failure
    assert wrapped.record_errors == 4


def test_negative_clock_is_preserved_as_evidence_without_negative_duration():
    clock = Clock(-100)
    rows, record = collector()
    wrapped = api().TimingTransport(DelayedTransport(clock), record, clock_ns=clock)
    assert wrapped.write(b'abc') == 3
    assert rows[-1]['host_start_ns'] == -100
    assert rows[-1]['host_end_ns'] == -60
    assert rows[-1]['duration_ns'] is None
    report = api().summarize_timing(rows)
    assert report['command_write_duration_ns']['count'] == 0
    json.dumps(report, allow_nan=False)


def test_sequence_present_before_write_is_not_a_new_acknowledgement():
    records = [state(90, 1, seq=1), *write_rows(1, 100, 110), state(150, 2, seq=1)]
    ack = api().summarize_timing(records)['acknowledgements']
    assert ack['written_actions'] == 1
    assert ack['observed_sequences'] == 0
    assert ack['ambiguous_sequences'] == 1
    assert ack['samples'][0]['status'] == 'ambiguous_sequence'


def test_incomplete_or_corrupt_writes_cannot_create_acknowledgements_or_nonfinite_json():
    corrupt = write_rows(1, 100, 110, sid=float('inf'))
    orphan_end = write_rows(2, 200, 210)[1:]
    missing_end = write_rows(3, 300, 310)[:1]
    report = api().summarize_timing([*corrupt, *orphan_end, *missing_end, state(350, 1, seq=3)])
    assert report['acknowledgements']['written_actions'] == 0
    assert report['counts']['incomplete_write_events'] == 2
    json.dumps(report, allow_nan=False)
