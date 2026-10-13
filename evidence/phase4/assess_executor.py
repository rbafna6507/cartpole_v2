"""Offline assessment of the parent-captured executor characterization report.

No Rig construction, device access or motion. Preserve source archive and command
procedure externally before calling. Commanded acceleration is the sampled MCU
state.acceleration, never the subsequently issued demand in the same row.
"""
import argparse
from dataclasses import replace
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from cartpole_sdk.identification import FitConfig, identify_pendulum
from cartpole_sdk.recording import strict_json_loads


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess(source, output_dir, procedure, log):
    raw = gzip.decompress(source.read_bytes())
    report = strict_json_loads(raw.decode())
    if report.get('ok') is not True: raise ValueError('source characterization did not complete successfully')
    info = report['info']
    if info['encoder_upright_raw'] != 3485 or info['reference_saved'] is not True:
        raise ValueError('installed preserved encoder reference differs')
    if report['final']['flags'] & 2 or report['final']['fault'] or report['final']['misses']:
        raise ValueError('source final state is not disabled/fault-free with zero misses')
    canonical = {}
    summaries = []
    for trial in report['trials']:
        name = trial['name']
        rows = []
        for raw_row in trial['rows']:
            if raw_row['run_id'] != name: raise ValueError('row trial identity mismatch')
            row = {key:raw_row[key] for key in ('t_s','theta_rad','cart_acceleration_m_s2','valid','run_id','calibration_id','frame_id','clock_id')}
            row.update(source='magnetic', acceleration_kind='commanded')
            rows.append(row)
        canonical[name] = rows
        destination = output_dir / ('executor-' + name + '-rows.jsonl')
        destination.write_text(''.join(json.dumps(row, separators=(',',':')) + '\n' for row in rows))
        t = np.array([row['t_s'] for row in rows])
        q = np.unwrap([row['theta_rad'] for row in rows])
        a = np.array([row['cart_acceleration_m_s2'] for row in rows])
        demand = np.array([row['demand'] for row in trial['rows']])
        quiet = q[(t-t[0]>.2)&(t-t[0]<1.)]
        final = trial['final']
        summaries.append(dict(name=name, sample_count=len(rows), duration_s=float(t[-1]-t[0]),
                              max_gap_s=float(np.max(np.diff(t))), min_gap_s=float(np.min(np.diff(t))),
                              gaps_over_005_s=int(np.sum(np.diff(t)>.05)),
                              angle_unwrapped_span_rad=float(np.ptp(q)), angle_std_rad=float(np.std(q)),
                              theta_rad_range=[float(q.min()),float(q.max())],
                              median_hanging_pi_difference_rad=float(np.median(q)-math.pi),
                              early_ramp_hanging_pi_difference_rad=float(np.median(quiet)-math.pi),
                              command_acceleration_std_m_s2=float(np.std(a)),command_acceleration_range_m_s2=[float(a.min()),float(a.max())],
                              requested_demand_std_m_s2=float(np.std(demand)),requested_demand_range_m_s2=[float(demand.min()),float(demand.max())],
                              request_at_clip_count=int(np.sum(np.abs(demand)>.249999)),
                              step_cart_peak_abs_m=max(abs(row['x_m']) for row in trial['rows']),
                              step_cart_velocity_peak_abs_m_s=max(abs(row['v_m_s']) for row in trial['rows']),
                              final_disabled=not bool(final['flags']&2), final_fault=final['fault'], final_misses=final['misses'],
                              amplitude_m=trial['amplitude_m'],frequencies_hz=trial['frequencies_hz'],
                              canonical_file=str(destination),canonical_sha256=sha(destination),
                              omega_omitted='filtered firmware omega effective timestamp is unknown',
                              acceleration_basis='sampled MCU commanded/profile acceleration; not subsequently sent demand; not independent cart measurement'))
    provenance=dict(source_gzip_sha256=sha(source),decoded_json_sha256=hashlib.sha256(raw).hexdigest(),
                    command_procedure_sha256=sha(procedure),run_log_sha256=sha(log),generator_sha256=sha(Path(__file__)),
                    hardware_access=False,calibration_modified=False,source_position_basis=report['position_basis'],
                    source_info=info,planned_bounds=report['planned_bounds'],hard_host_guards=report['hard_host_guards'])
    raw_fit = identify_pendulum(canonical['train1'],canonical['validation1'],source='magnetic',acceleration_kind='commanded',provenance=provenance)
    # This value was parent-reported before these trials from an independent
    # hanging equilibrium. It is a fixed sensitivity assumption, not selected
    # from validation and not a verified/calibrated global encoder correction.
    sensitivity_offset = 3.03-math.pi
    sensitivity = identify_pendulum(canonical['train1'],canonical['validation1'],source='magnetic',acceleration_kind='commanded',
                                   config=replace(FitConfig(),angle_offset_rad=sensitivity_offset),
                                   provenance=dict(provenance,offset_basis='prior parent-reported hanging equilibrium3.03rad; sensitivity only; not commissioned correction'))
    result=dict(kind='actual low-amplitude executor characterization identification assessment',datasets=summaries,provenance=provenance,
                unmodified_encoder_fit=raw_fit.to_dict(),
                fixed_prior_offset_sensitivity=dict(assumed_offset_rad=sensitivity_offset,physical_acceptance_allowed=False,report=sensitivity.to_dict()),
                accepted_physical_model=raw_fit.accepted,recommended_physical_model=raw_fit.recommended_model,
                limitations=['Both cart displacement/velocity and sampled acceleration derive from executor step/profile state',
                             'PD40/8 feedback on step-derived cart state contributes to commanded input; gain/delay are composite quantities',
                             'Reported hanging bias may be angle dependent; a local hanging offset is not a calibrated global upright correction',
                             'One pair of low-amplitude trials does not replace repeated trials and independent cart/angle measurements',
                             'No known-rate timestamp for filtered omega; angle-only heldout initialization',
                             'Sensitivity result cannot establish physical calibration or commission a model'])
    output_dir.joinpath('executor-characterization-assessment.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--procedure',type=Path,required=True)
    parser.add_argument('--log',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    result=assess(args.source,args.output_dir,args.procedure,args.log)
    print(json.dumps(dict(datasets=result['datasets'],accepted_physical_model=result['accepted_physical_model'],
                          reports={label:dict(accepted=fit['accepted'],reasons=fit['reasons'],parameters=fit['parameters'],
                                              training={k:v for k,v in fit['training'].items() if k!='delay_profile'},validation=fit['validation'])
                                   for label,fit in [('unmodified_encoder',result['unmodified_encoder_fit']),
                                                     ('fixed_prior_offset_sensitivity',result['fixed_prior_offset_sensitivity']['report'])]}),indent=2))
