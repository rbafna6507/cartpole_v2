"""Synthetic clock/column regressions. No rig dependency or device access."""
import json
from pathlib import Path
import tempfile
import unittest

from analyze_timing import FIELDS, STAGES, analyze, decode_trace, interval, quantiles


def record(stage, start, finish, cpu_start, cpu_finish, incoming=-1, outgoing=-1, board=-1):
    return [stage,start,cpu_start,finish,cpu_finish,incoming,-1,outgoing,board,0]


def packed(rows):
    return dict(fields=FIELDS,stages=STAGES,count=len(rows),dropped=0,native_id=123,
                columns=[list(x) for x in zip(*rows)])


class TimingAnalysisTests(unittest.TestCase):
    def test_schema_rejects_truncated_column(self):
        data=packed([record(0,0,10,0,5,outgoing=1,board=1)])
        data['columns'][2]=[]
        with self.assertRaises(ValueError):decode_trace(data)

    def test_quantiles_include_empty_and_interpolation(self):
        self.assertEqual(quantiles([]),{'n':0})
        self.assertEqual(quantiles([1,3])['p50'],2)
        self.assertAlmostEqual(quantiles([1,3])['p95'],2.9)

    def test_wait_time_is_not_reported_as_cpu_work(self):
        rows=decode_trace(packed([
            record(0,0,100,0,80,outgoing=100,board=100_000_000),
            record(1,110,160,90,130,incoming=100),
            record(3,170,12_000_170,140,200,incoming=100,outgoing=112,board=112_000_000),
            record(0,12_000_180,12_000_280,210,290,outgoing=112,board=112_000_000)]))
        result=interval(rows[0],rows[-1],rows)
        self.assertEqual(result['board_gap_ns'],12_000_000)
        self.assertEqual(result['classification'],'wait')
        self.assertTrue(result['off_thread_cpu_time_dominates'])
        self.assertEqual(result['thread_cpu_ns'],210)
        self.assertEqual(sum(result['stage_wall_ns'].values())+result['between_stage_wall_ns'],result['host_wall_ns'])

    def test_preflight_excluded_and_post_send_step_tail_located(self):
        rows=[record(0,0,100_000,0,80_000,outgoing=0,board=0),
              record(0,100_000_000,100_100_000,100_000,180_000,outgoing=100,board=100_000_000),
              record(1,100_110_000,100_200_000,190_000,240_000,incoming=100),
              record(2,100_210_000,108_210_000,250_000,450_000,incoming=100,outgoing=108,board=108_000_000),
              record(3,108_220_000,108_230_000,460_000,465_000,incoming=100,outgoing=108,board=108_000_000),
              record(0,108_240_000,108_340_000,470_000,550_000,outgoing=108,board=108_000_000),
              record(1,108_350_000,108_450_000,560_000,600_000,incoming=108)]
        report=dict(case='zero',rate_hz=250,log='rig.jsonl',timing_summary=dict(observations=3,max_observation_gap_ns=100_000_000))
        events=[dict(type='command',host_monotonic_ns=100_310_000,payload='V2 A 99 1 100 20 0'),
                dict(type='action_request',host_monotonic_ns=100_410_000,request=dict(sequence=1,observation_sequence=100)),
                dict(type='state',host_monotonic_ns=104_110_000,state=dict(unwrapped_tick=104,received_ns=104_100_000))]
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'timing.json').write_text(json.dumps(packed(rows)))
            (d/'report.json').write_text(json.dumps(report))
            (d/'rig.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
            result=analyze(d)
        self.assertEqual(result['active_observations'],2)
        self.assertEqual(len(result['excluded_unacted_observations']),1)
        self.assertTrue(result['raw_summary_matches_instrumentation'])
        self.assertEqual(result['active_observation_gap_counts_ns'],{8_000_000:1})
        longest=result['worst_intervals_by_board_gap'][0]
        self.assertEqual(longest['classification'],'step_post_action_record_tail')
        self.assertEqual(longest['step_log_splits'][0]['post_action_record_tail_ns'],7_800_000)
        self.assertEqual(longest['wait_receipt_timeline'][0]['first_newer_receipt_to_wait_return_ns'],4_130_000)
        self.assertAlmostEqual(result['step_log_split_summary']['pre_command_record_ms']['max'],.1)

    def test_clock_overhead_may_make_cpu_slightly_exceed_wall(self):
        rows=decode_trace(packed([record(0,0,100,0,101,outgoing=1,board=1)]))
        self.assertEqual(rows[0]['wall_minus_cpu_ns'],-1)

    def test_rolling_budget_excludes_exact_one_second_boundary(self):
        from analyze_timing_v2 import rolling_gap_summary
        gaps=[dict(observation_sequence=i,board_ns=t,board_gap_ns=8_000_000)
              for i,t in enumerate((0,500_000_000,1_000_000_000))]
        self.assertEqual(rolling_gap_summary(gaps)['maximum_count'],2)
        self.assertEqual(rolling_gap_summary(gaps)['events_exceeding_two'],0)
        gaps.append(dict(observation_sequence=3,board_ns=1_004_000_000,board_gap_ns=8_000_000))
        result=rolling_gap_summary(gaps)
        self.assertEqual(result['maximum_count'],3)
        self.assertEqual([x['observation_sequence'] for x in result['worst_members']],[1,2,3])

    def test_terminal_wait_is_excluded_from_active_interval_max(self):
        from analyze_timing_v2 import analyze as analyze_v2
        rows=[record(0,0,100,0,80,outgoing=100,board=100_000_000),
              record(1,110,160,90,130,incoming=100),
              record(3,170,4_000_170,140,200,incoming=100,outgoing=104,board=104_000_000),
              record(0,4_000_180,4_000_280,210,290,outgoing=104,board=104_000_000),
              record(1,4_000_290,4_000_340,300,340,incoming=104),
              record(3,4_000_350,24_000_350,350,450,incoming=104)]
        rows[-1][-1]=1
        report=dict(case='observe',rate_hz=250,log=None,timing_summary=dict(observations=2,max_observation_gap_ns=4_000_000))
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            (d/'timing.json').write_text(json.dumps(packed(rows)))
            (d/'report.json').write_text(json.dumps(report))
            result=analyze_v2(d)
        self.assertEqual(result['stage_summary']['wait']['wall_ms']['max'],20)
        self.assertEqual(result['active_interval_stage_summary']['wait']['wall_ms']['max'],4)
        self.assertEqual(result['terminal_stages'][-1]['error'],1)


if __name__=='__main__':unittest.main()
