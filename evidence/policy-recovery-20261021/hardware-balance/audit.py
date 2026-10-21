#!/usr/bin/env python3
"""Offline audit of preserved filtered BAL trials; no device or network imports."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
TRIALS = {
    'filtered-bal-run5-01': ('camera-filtered-01', False),
    'filtered-bal-run25-01': ('camera-filtered-25-01', False),
    'filtered-bal-run25-02': ('camera-filtered-25-02', False),
    'filtered-console-run25-03': ('camera-filtered-console-03', True),
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def stats(values):
    values = list(values)
    assert values and all(math.isfinite(v) for v in values)
    return dict(n=len(values), min=min(values), max=max(values),
                mean=sum(values)/len(values),
                rms=math.sqrt(sum(v*v for v in values)/len(values)))


def audit_trial(folder, camera, disturbed, manifest, actor):
    paths = list(folder.glob('rig-*.jsonl'))
    assert len(paths) == 1
    path = paths[0]
    assert digest(path) == manifest[f'{folder.name}/{path.name}']['sha256']
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    states = {}; infos = []; commands = []; preflight = []
    for row in rows:
        if row['type'] == 'state':
            state = row['state']
            states.setdefault((state['sid'], state['unwrapped_tick']), state)
        elif row['type'] == 'info': infos.append(row['info'])
        elif row['type'] == 'command': commands.append(row)
        elif row['type'] == 'neural_preflight': preflight.append(row)
    states = list(states.values())
    active = [s for s in states if s['flags'] & 2]
    assert active and all(s['mode'] == 12 for s in active)
    after = next(s for s in states if s['unwrapped_tick'] > active[-1]['unwrapped_tick'])
    assert not after['flags'] & 2
    starts = [r for r in rows if r['type'] == 'policy_start']
    ends = [r for r in rows if r['type'] == 'policy_end']
    assert len(starts) == len(ends) == 1
    start, end = starts[0], ends[0]
    arm = next(r for r in commands if r['payload'].split()[1] == 'ARM')
    stop = next(r for r in commands if r['payload'].split()[1] == 'STOP' and
                r['host_monotonic_ns'] > arm['host_monotonic_ns'])
    actions = [r for r in rows if r['type'] == 'action_request']
    assert len(actions) == end['calls']
    assert all(p['actor_sha256'] == actor['content_sha256'] and
               p['encoder_reference']['upright_raw'] == 450 and
               p['observation_contract']['angle_source'] == 'filtered' and
               p['executor_parameters']['bw'] == 10 and
               p['executor_parameters']['jmax'] == 150 for p in preflight)
    assert preflight and all(i['encoder_upright_raw'] == 450 for i in infos)
    metric = lambda sub: dict(raw_angle_deg=stats(math.degrees(s['theta']) for s in sub),
        filtered_angle_deg=stats(math.degrees(s['angle_hat']) for s in sub),
        counted_x_m=stats(s['x'] for s in sub),
        observer_omega_rad_s=stats(s['omega'] for s in sub),
        commanded_velocity_m_s=stats(s['velocity'] for s in sub),
        governed_acceleration_m_s2=stats(s['acceleration'] for s in sub))
    camera_path = camera/'vision.ndjson'
    assert digest(camera_path) == manifest[f'{camera.name}/vision.ndjson']['sha256']
    # Only the camera's own frame timestamps/validity count here; embedded encoder packets can be stale.
    frames = {}
    for line in camera_path.read_text().splitlines():
        row = json.loads(line); v = row.get('vision') or {}; t = v.get('t')
        if isinstance(t, (int, float)):
            frames.setdefault((v.get('seq'), t), v)
    coverage = [v for v in frames.values() if active[0]['received_ns']/1e9 <= v['t'] <= after['received_ns']/1e9]
    termination = [r for r in rows if r['type'] == 'termination']
    report_path = folder/'report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    if report:
        assert digest(report_path) == manifest[f'{folder.name}/report.json']['sha256']
        assert report['actor_file_sha256'] == digest(ROOT/'training/candidates/balance-recovery-20261021/actor.json')
    return dict(trial=folder.name, operator_pokes_reported=disturbed,
        disturbance_basis='User explicitly confirmed only filtered-console-run25-03 had pokes; timestamps and magnitudes unspecified.',
        source=dict(path=str(path.relative_to(ROOT)), sha256=digest(path)),
        camera=dict(path=str(camera_path.relative_to(ROOT)), sha256=digest(camera_path),
                    frames_in_active_receipt_interval=len(coverage),
                    valid_angle_frames=sum(v.get('angle_valid') is True for v in coverage),
                    embedded_encoder_ignored=True),
        requested_duration_s=start['duration_s'],
        host_arm_to_stop_command_s=(stop['host_monotonic_ns']-arm['host_monotonic_ns'])/1e9,
        host_policy_record_span_s=(end['host_monotonic_ns']-start['host_monotonic_ns'])/1e9,
        board_first_enabled_to_first_disabled_s=(after['unwrapped_us']-active[0]['unwrapped_us'])/1e6,
        sampled_active_span_s=(active[-1]['unwrapped_us']-active[0]['unwrapped_us'])/1e6,
        active_samples=len(active), metrics=metric(active),
        final_five_seconds=metric([s for s in active if s['unwrapped_us'] >= active[-1]['unwrapped_us']-5_000_000]),
        active_faults=sorted({s['fault'] for s in active}), all_observed_faults=sorted({s['fault'] for s in states}),
        rail_brake_samples=sum(bool(s['brake_direction']) for s in active),
        first_enabled=active[0], last_enabled=active[-1], first_disabled=after,
        action_requests=len(actions), action_ttl_ms=sorted({(r['request']['expires_at_ns']-r['request']['issued_at_ns'])/1e6 for r in actions}),
        action_request_gap_ms=stats((b['host_monotonic_ns']-a['host_monotonic_ns'])/1e6 for a,b in zip(actions,actions[1:])),
        inference_mean_ms=end['mean_compute_ns']/1e6, inference_max_ms=end['max_compute_ns']/1e6,
        i2c_errors_observed=sorted({i['i2c_errors'] for i in infos}),
        executor_parameters=preflight[-1]['executor_parameters'],
        runtime_environment=None if report is None else report['runtime_environment'],
        driver_report_success=None if report is None else report['success'],
        termination=termination, hardware_accepted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Use a fresh output path'
    manifest_path = EVIDENCE/'remote-files.json'
    manifest = json.loads(manifest_path.read_text())
    actor_path = ROOT/'training/candidates/balance-recovery-20261021/actor.json'
    receipt_path = actor_path.with_name('receipt.json')
    actor = json.loads(actor_path.read_text()); receipt = json.loads(receipt_path.read_text())
    assert digest(actor_path) == receipt['actor_file_sha256']
    assert receipt['ppo_updates'] == receipt['environment_training_steps'] == 0
    root = ROOT/'runs/policy-recovery-20261021/hardware-live'
    result = dict(schema='cartpole-filtered-hardware-balance-audit-v1',
        script_sha256=digest(Path(__file__)), remote_manifest_sha256=digest(manifest_path),
        actor_file_sha256=digest(actor_path), actor_content_sha256=actor['content_sha256'],
        actor_receipt_sha256=digest(receipt_path), ppo_updates=receipt['ppo_updates'],
        actor_training='Supervised approximation of actual filtered native BAL feedback',
        hardware_accepted=False, serial_or_motion_activity=False,
        trials=[audit_trial(root/name, root/camera, disturbed, manifest, actor)
                for name,(camera,disturbed) in TRIALS.items()])
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps([dict(trial=t['trial'], arm_to_stop_s=t['host_arm_to_stop_command_s'],
        active_span_s=t['sampled_active_span_s'], raw_angle_rms_deg=t['metrics']['raw_angle_deg']['rms'],
        x_rms_m=t['metrics']['counted_x_m']['rms'], x_min_m=t['metrics']['counted_x_m']['min'],
        x_max_m=t['metrics']['counted_x_m']['max'], faults=t['active_faults'], disturbed=t['operator_pokes_reported'])
        for t in result['trials']],indent=2))


if __name__ == '__main__':
    main()
