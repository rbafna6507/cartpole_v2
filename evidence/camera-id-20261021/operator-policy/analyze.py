"""Offline deterministic replay only: no Rig instance or transport is constructed."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo
from cartpole_sdk.contracts import Session, Topology, Acceleration
from cartpole_sdk.policies import neural
from cartpole_sdk.policies.neural import load_neural_policy, RUNTIME_FILES
from cartpole_sdk.policies.rig_observation import rig_channels
from cartpole_sdk.learning.balance_hardware import BalanceOnlyPolicy
from cartpole_sdk.rig.client import Rig
from cartpole_sdk.rig.protocol import State

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(logs_dir, actor_path, archive_path):
    paths = sorted(logs_dir.rglob('rig-*.jsonl'))
    if not paths:
        raise ValueError(f'no rig-*.jsonl files found under {logs_dir}')
    sdk_root = Path(neural.__file__).resolve().parents[1]
    loaded=load_neural_policy(actor_path,channels=rig_channels(angle_source='raw'))
    results=dict(archive_path=str(archive_path), archive_sha256=sha(archive_path),
        analysis_source_sha256=sha(Path(__file__)),
        actor_path=str(actor_path),actor_file_sha256=sha(actor_path),actor_content_sha256=loaded.actor['content_sha256'],
        actor_scale_m_s2=loaded.actor['action_scale_m_s2'], actor_runtime_pins_verified=True,
        boundary_source_sha256=sha(sdk_root/'learning/balance_hardware.py'),
        boundary_pinned_in_actor='learning/balance_hardware.py' in RUNTIME_FILES, runs=[])
    for path in paths:
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        def of(kind): return [r for r in rows if r['type']==kind]
        boundary=of('balance_only_boundary')[0]
        assert boundary['actor_sha256']==loaded.actor['content_sha256']
        state_rows=of('state'); states={r['state']['unwrapped_tick']: r['state'] for r in state_rows}
        session_data=of('session')[0]['session']
        session=Session(session_data['session_id'],session_data['clock_id'],Topology())
        fake=SimpleNamespace(session=session, _require=lambda: None, _fresh=lambda state: None)
        fake._observation=lambda state: Rig._observation(fake,state)
        def observation(s):
            fake.state=State(**s)
            return Rig.control_observation(fake)
        policy=BalanceOnlyPolicy(loaded.actor,channels=loaded.channels,guard_profile=boundary.get('guard_profile','commissioning'))
        policy.reset(session)
        replay=[]
        for row in of('action_request'):
            req=row['request']; s=states[req['observation_sequence']]
            obs=observation(s); result=policy.act(obs)
            assert isinstance(result,Acceleration), policy.fault_reason
            delta=result.acceleration_m_s2-req['acceleration_m_s2']
            assert abs(delta)<1e-12, (path,delta)
            replay.append(dict(sequence=obs.sequence,board_ns=obs.available_ns,host_request_ns=row['host_monotonic_ns'],
                demand_m_s2=result.acceleration_m_s2,replay_difference_m_s2=delta,state=s))
        failure=of('policy_failure')
        failed=None
        if failure:
            fail=failure[0]
            s=states[fail['failed_observation_sequence']]
            if fail['act_started_host_ns'] is not None:
                intent=policy.act(observation(s))
                failed=dict(state=s, inferred_intent_type=type(intent).__name__,
                    demand_m_s2=intent.acceleration_m_s2 if isinstance(intent,Acceleration) else None,
                    replay_fault_reason=policy.fault_reason)
            else:
                failed=dict(state=s, inferred_intent_type=None,demand_m_s2=None,replay_fault_reason=None)
        arm=[r for r in of('reply') if r['payload'].endswith(' ARM')]
        stops=[r for r in of('reply') if r['payload'].endswith(' STOP')]
        enabled=[r['state'] for r in state_rows if r['state']['flags']&2]
        run=dict(path=str(path),file_sha256=sha(path),
            start_wall_local=datetime.fromtimestamp(int(path.name.split('-')[1])/1e9,ZoneInfo('America/Detroit')).isoformat(),
            boundary=boundary,policy_start=of('policy_start'),policy_end=of('policy_end'),
            failure=failure,failed_prediction=failed,replayed_actions=replay,
            accepted_action_requests=len(replay),arm_ack_count=len(arm),stop_ack_count=len(stops),
            stop_failures=of('stop_failure'),termination=of('termination'),
            initial_state=state_rows[0]['state'],final_state=state_rows[-1]['state'],
            enabled_samples=len(enabled),enabled_first_to_last_board_s=(enabled[-1]['unwrapped_us']-enabled[0]['unwrapped_us'])/1e6 if enabled else None,
            max_abs_enabled_state={k:max((abs(s[k]) for s in enabled),default=None) for k in ('x','velocity','acceleration','theta','omega')},
            unique_faults=sorted({r['state']['fault'] for r in state_rows}),
            telemetry_dropped_delta=state_rows[-1]['state']['dropped']-state_rows[0]['state']['dropped'],
            misses_delta=state_rows[-1]['state']['misses']-state_rows[0]['state']['misses'])
        if arm and failure:
            run['arm_ack_to_failure_s']=(failure[0]['host_monotonic_ns']-arm[0]['host_monotonic_ns'])/1e9
            run['arm_ack_to_first_stop_ack_s']=(stops[0]['host_monotonic_ns']-arm[0]['host_monotonic_ns'])/1e9
            run['failure_to_stop_ack_ms']=(stops[0]['host_monotonic_ns']-failure[0]['host_monotonic_ns'])/1e6
            run['first_action_anchor_to_failure_board_s']=(failure[0]['failed_observation_board_ns']-replay[0]['board_ns'])/1e9 if replay else None
        results['runs'].append(run)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--logs-dir', required=True, type=Path,
                        help='User-extracted log directory; recursively reads rig-*.jsonl files.')
    parser.add_argument('--actor', required=True, type=Path,
                        help='Unchanged numeric actor JSON; content and runtime pins are verified.')
    parser.add_argument('--archive', required=True, type=Path,
                        help='Original archive to hash for provenance; this script never extracts it.')
    parser.add_argument('--output', required=True, type=Path,
                        help='New JSON output file; refuses to overwrite an existing result.')
    args = parser.parse_args(argv)
    args.output = args.output.resolve()
    if args.output.exists():
        parser.error('output already exists; select a new output path')
    results = analyze(args.logs_dir.resolve(), args.actor.resolve(), args.archive.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(results, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('output:', args.output)
    print('actor:',results['actor_file_sha256'], results['actor_content_sha256'])
    print('source:',results['boundary_source_sha256'], 'pinned:',results['boundary_pinned_in_actor'])
    for r in results['runs']:
        print(Path(r['path']).name, r['start_wall_local'])
        print('actions',r['accepted_action_requests'],'calls',r['policy_end'],'arm',r['arm_ack_count'],'stopacks',r['stop_ack_count'],'enabledspan',r['enabled_first_to_last_board_s'])
        print('arm-failure',r.get('arm_ack_to_failure_s'),'arm-stop',r.get('arm_ack_to_first_stop_ack_s'),'failure-stopms',r.get('failure_to_stop_ack_ms'))
        print('failure',r['failure'][0]['reason'] if r['failure'] else None)
        if r['failed_prediction']: print('failed prediction:',r['failed_prediction'])
        print('demands',[p['demand_m_s2'] for p in r['replayed_actions']])
        print('faults/drops/misses',r['unique_faults'],r['telemetry_dropped_delta'],r['misses_delta'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
