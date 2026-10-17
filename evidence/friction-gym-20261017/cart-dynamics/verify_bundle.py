#!/usr/bin/env python3
"""Read-only binding and numerical checks across the final audit bundle."""
import hashlib,json,math
from pathlib import Path
base=Path(__file__).resolve().parent
root=base.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
a=read(base/'results-v1/report.json');v=read(base/'results-v1/verification.json');b=read(base/'backend-profile-v1/report.json');r=read(base/'velocity-reconstruction-v1/report.json')
assert v['passed'] and v['report_sha256']==sha(base/'results-v1/report.json')
for report,script in [(a,'audit.py'),(b,'backend_replay.py'),(r,'reconstruction_replay.py')]:
 assert report['provenance']['script_sha256']==sha(base/script)
 assert report['accepted'] is False
assert r['parameters_fitted'] is False and b['hardware_validated'] is r['hardware_validated'] is False
assert b['config']==r['config'] and b['config']['rail_half_m']==.308962494
assert b['provenance']['audit_sha256']==r['provenance']['audit_sha256']==sha(base/'results-v1/report.json')
assert r['provenance']['previous_backend_report_sha256']==sha(base/'backend-profile-v1/report.json')
for report in [b,r]:
 for path,value in report['provenance']['source_sha256'].items():assert sha(root/path)==value,(path,'production source changed after recorded run')
assert a['provenance']['freeze_sha256']==sha(root/'evidence/system-id-model-review-20261017/candidate-freeze-latest6.json')
assert b['aggregate_vs_encoder']['samples']==r['aggregate']['sampled_acceleration']['samples']==r['aggregate']['velocity_endpoint_acceleration']['samples']==2137
assert b['aggregate_vs_encoder']==r['aggregate']['sampled_acceleration']
for ar,br,rr in zip(a['runs'],b['runs'],r['runs']):
 assert ar['source_sha256']==br['source_sha256']==rr['source_sha256']
 assert rr['initial_state']==br['initial_state']
 assert ar['source_status']['completed'] and ar['source_status']['stop_confirmed'] and ar['source_status']['records_dropped']==0
 assert ar['source_status']['collector_result']['policy']['clamped_commands']==(2 if '30' in ar['name'] else 0)
 m=rr['methods'];assert m['sampled_acceleration']['trace']['t_s']==m['velocity_endpoint_acceleration']['trace']['t_s']
 assert m['sampled_acceleration']['optical_trace']['t_s']==m['velocity_endpoint_acceleration']['optical_trace']['t_s']
 for method in m.values():assert method['force_saturated_ticks']==0 and method['cart_acceleration_tracking_m_s2']['max_abs']<1e-10
 assert m['velocity_endpoint_acceleration']['velocity_vs_reconstructed_endpoints_m_s']['max_abs']<2e-11
 assert m['velocity_endpoint_acceleration']['cart_vs_counts_mm']['max_abs']<.3
 assert m['velocity_endpoint_acceleration']['optical_position_residual_px']['rms']<.32
assert v['weak_form_residuals']['training']['integral_nrmse']>.15
result=dict(schema='cartpole-cart-audit-bundle-verification-v1',passed=True,checks=['audit/source/verification hashes','frozen model parameters and explicit rejected statuses','matching profile config and production source hashes','identical raw-input replay metrics','six source identities and preserved two30mmclamp deviations','same initial conditions and scored samples','identical optical support','velocity reconstruction targets matched','sub0.3mm count reconstruction','sub0.32px optical shape residual','original training weak residual remains above0.15'],report_sha256={str(p.relative_to(base)):sha(p) for p in [base/'results-v1/report.json',base/'backend-profile-v1/report.json',base/'velocity-reconstruction-v1/report.json']},script_sha256=sha(Path(__file__)))
p=base/'verification.json'
if p.exists():raise SystemExit('preserve existing verification')
p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
