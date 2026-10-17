#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26,<3", "matplotlib>=3.8,<4"]
# ///
"""Summarize frozen passive-refinement evidence without fitting or selecting anew."""
import argparse,datetime,gzip,hashlib,json,math,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parents[1]
def read(p):
    p=Path(p);data=p.read_bytes();return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):
    if p.exists():raise FileExistsError(p)
    p.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def errors(row,key):
    return np.array(row['short_errors_rad'] if key=='short' else row['continuous'][key]['errors_rad'])
def pooled(records,key):
    e=np.concatenate([errors(r,key) for rec in records for r in rec['releases']]);return dict(rms_deg=float(np.rad2deg(np.sqrt(np.mean(e**2)))),p95_deg=float(np.rad2deg(np.quantile(abs(e),.95))),samples=len(e))
def pooled_all(records):return {k:pooled(records,k) for k in ['short','.25','.5']}
def bootstrap(baseline,candidate):
    rng=np.random.default_rng(20261017);out={}
    for key in ['short','.25','.5']:
        groups=[]
        for b,c in zip(baseline,candidate):
            assert b['label']==c['label']
            rows=[]
            for br,cr in zip(b['releases'],c['releases']):
                assert br['episode_id']==cr['episode_id']
                be=errors(br,key);ce=errors(cr,key);assert len(be)==len(ce)
                rows.append([float(be@be),float(ce@ce),len(be)])
            groups.append(np.array(rows))
        samples=[]
        for _ in range(4000):
            totals=sum((g[rng.integers(0,len(g),len(g))].sum(axis=0) for g in groups),start=np.zeros(3))
            samples.append(float(np.rad2deg(np.sqrt(totals[1]/totals[2])-np.sqrt(totals[0]/totals[2]))))
        out[key]=dict(candidate_minus_baseline_rms_deg=float(pooled(candidate,key)['rms_deg']-pooled(baseline,key)['rms_deg']),paired_release_bootstrap_95pct_interval_deg=np.quantile(samples,[.025,.975]).tolist(),resamples=4000,seed=20261017)
    return dict(metrics=out,interpretation='Descriptive conditional paired release bootstrap stratified within each of only two regression recordings. It does not account for recording-level dependence, calibration bias, prior inspection or model selection; not a confidence guarantee for new sessions.')
def fmt(m):return f"{m['rms_deg']:.3f} / {m['p95_deg']:.3f}"
def plot_record(out,label,baseline,candidate,quality,source):
    n=len(baseline['releases']);fig,axes=plt.subplots(math.ceil(n/3),3,figsize=(16,3.0*math.ceil(n/3)),squeeze=False)
    q0=source['identity']['passive_baseline']['encoder']['raw_angle_rad']
    for ax,b,c,q in zip(axes.flat,baseline['releases'],candidate['releases'],quality):
        bb=b['continuous']['.5'];cc=c['continuous']['.5'];t=np.array(bb['t_s']);t=t-t[0]
        center=q0+2*np.pi*round((float(np.median(bb['observed_rad']))-q0)/(2*np.pi))
        ax.plot(t,np.rad2deg(np.array(bb['observed_rad'])-center),color='#20242b',lw=1,label='Encoder')
        ax.plot(t,np.rad2deg(np.array(bb['predicted_rad'])-center),color='#d08b26',lw=1,label='Frozen baseline')
        ax.plot(t,np.rad2deg(np.array(cc['predicted_rad'])-center),color='#0067a6',lw=1,label='Selected candidate')
        flags=('camera FAIL ' if not q['passed'] else '')+('pose FAIL' if not q['pose_verified'] else '')
        ax.set_title(f"{b['episode_id']} · RMS {bb['metrics']['rms_deg']:.2f}° → {cc['metrics']['rms_deg']:.2f}°\n{flags or 'Camera / pose screens pass'}",fontsize=9,color='#a42d2d' if flags else '#20242b')
        ax.grid(alpha=.2);ax.set_xlabel('Seconds after 0.5 s initialization',fontsize=8);ax.set_ylabel('Angle about recorded hanging (°)',fontsize=8);ax.tick_params(labelsize=8)
    for ax in axes.flat[n:]:ax.axis('off')
    axes.flat[0].legend(fontsize=8,loc='best')
    fig.suptitle(f'{label}: uninterrupted forecasts after one causal initialization\nAll annotated releases retained; encoder coordinates are not absolute angle calibration',fontsize=13)
    fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(out/f'{label}-comparison.png',dpi=150);plt.close(fig)
def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,default=HERE);a=p.parse_args();out=a.evidence
    freeze=read(out/'candidate-freeze.json');tr=read(out/'training.json.gz');reg=read(out/'regression.json.gz')
    assert reg['freeze_sha256']==sha(out/'candidate-freeze.json')
    assert freeze['training_report_sha256']==sha(out/'training.json.gz')
    assert freeze['created_at_utc']<reg['created_at_utc']
    for path,digest in freeze['method_hashes'].items():assert sha(ROOT/path)==digest,path
    bm=next(m for m in tr['models'] if m['name']=='baseline/frozen_rawq');cm=next(m for m in tr['models'] if m['name']==freeze['candidate_name'])
    rb=next(m for m in reg['models'] if m['name']=='baseline')['records'];rc=next(m for m in reg['models'] if m['name']=='candidate')['records']
    baseline=bm['records']+rb;candidate=cm['records']+rc;sources=tr['source_identities']+reg['source_identities']
    assert {r['label'] for r in tr['source_identities']}=={'training6','development6','training8','training9'}
    assert {r['label'] for r in reg['source_identities']}=={'validation8','validation9'}
    assert not set(freeze['development_source_sha256'])&{r['identity']['sha256'] for r in reg['source_identities']}
    parity=[];old=read(ROOT/'evidence/passive-batches8-9-20261017/all4-summary.json')
    for b in baseline:
        if b['label'] not in ['training8','training9','validation8','validation9']:continue
        prior=next(r for r in old['recordings'] if r['label']==b['label']);m=next(m for m in prior['models'] if m['model']=='weak_coulomb')
        for key in ['short','.25','.5']:
            x=m['short'] if key=='short' else next(h['metrics'] for h in m['continuous_after_history'] if h['warmup_s']==float(key))
            assert x['samples']==b['metrics'][key]['samples']
            differences={name:abs(x[name]-b['metrics'][key][name]) for name in ['rms_deg','p95_deg']}
            assert max(differences.values())<1e-8,(b['label'],key,differences)
            parity.append(dict(label=b['label'],metric=key,differences_deg=differences))
    for b,c,s in zip(baseline,candidate,sources):
        assert b['label']==c['label']==s['label']
        assert not b['skipped'] and not c['skipped']
        assert len(b['releases'])==len(c['releases'])==len(s['quality']['episodes'])==len(s['identity']['selection'])
        for br,cr in zip(b['releases'],c['releases']):
            assert br['episode_id']==cr['episode_id']
            for key in ['short','.25','.5']:assert len(errors(br,key))==len(errors(cr,key))
        assert sha(ROOT/s['annotations'])==s['annotations_sha256']
        assert sha(ROOT/s['archive'])==s['archive_sha256']
    bp=pooled_all(rb);cp=pooled_all(rc)
    checks=dict(primary_improves_at_least_5pct=cp['.5']['rms_deg']<=.95*bp['.5']['rms_deg'],each_recording_primary_within_10pct=all(c['metrics']['.5']['rms_deg']<=1.1*b['metrics']['.5']['rms_deg'] for b,c in zip(rb,rc)),short_within_5pct=cp['short']['rms_deg']<=1.05*bp['short']['rms_deg'],quarter_history_within_5pct=cp['.25']['rms_deg']<=1.05*bp['.25']['rms_deg'],preserves_short_gates=all((not br['short_numeric_pass'] or cr['short_numeric_pass']) and (not br['short_coverage_pass'] or cr['short_coverage_pass']) for b,c in zip(rb,rc) for br,cr in zip(b['releases'],c['releases'])))
    qualifies=freeze['candidate_name']!='baseline/frozen_rawq' and all(checks.values())
    latest_b=[r for r in baseline if r['label'] not in ['training6','development6']];latest_c=[r for r in candidate if r['label'] not in ['training6','development6']]
    quality_counts={}
    for labels,name in [(['validation8','validation9'],'regression'),(['training8','training9','validation8','validation9'],'latest4'),([s['label'] for s in sources],'all6')]:
        q=[e for s in sources if s['label'] in labels for e in s['quality']['episodes']]
        quality_counts[name]=dict(releases=len(q),camera_pass=sum(e['passed'] for e in q),pose_pass=sum(e['pose_verified'] for e in q))
    gate_counts={m:{'numeric_pass':sum(r['short_numeric_pass'] for rec in rows for r in rec['releases']),'coverage_pass':sum(r['short_coverage_pass'] for rec in rows for r in rec['releases']),'releases':sum(len(rec['releases']) for rec in rows)} for m,rows in [('baseline',baseline),('candidate',candidate)]}
    summary=dict(short_gate_counts=gate_counts,created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),candidate_name=freeze['candidate_name'],parameters=freeze['parameters'],recommendation='candidate for development-only simulator evaluation' if qualifies else 'retain frozen baseline',regression_checks=checks,regression_pooled=dict(baseline=bp,candidate=cp),latest4_pooled=dict(baseline=pooled_all(latest_b),candidate=pooled_all(latest_c)),all_training_pooled=dict(baseline=pooled_all(bm['records']),candidate=pooled_all(cm['records'])),quality=quality_counts,uncertainty=bootstrap(rb,rc),freeze_sha256=sha(out/'candidate-freeze.json'),accepted=False,exported=False)
    save(out/'summary.json',summary)
    per=[]
    for b,c,s in zip(baseline,candidate,sources):
        plot_record(out,b['label'],b,c,s['quality']['episodes'],s)
        for br,cr,q in zip(b['releases'],c['releases'],s['quality']['episodes']):
            per.append(dict(label=b['label'],episode_id=br['episode_id'],baseline={k:br['short'] if k=='short' else br['continuous'][k]['metrics'] for k in ['short','.25','.5']},candidate={k:cr['short'] if k=='short' else cr['continuous'][k]['metrics'] for k in ['short','.25','.5']},short_windows=dict(baseline=len(br['short_windows']),candidate=len(cr['short_windows'])),short_numeric_pass=dict(baseline=br['short_numeric_pass'],candidate=cr['short_numeric_pass']),short_coverage_pass=dict(baseline=br['short_coverage_pass'],candidate=cr['short_coverage_pass']),camera_quality=q))
    save(out/'per-release.json',per)
    text=["# Passive refinement — training-only selection and frozen regression",'',f"**Recommendation: {summary['recommendation']}.** The training-selected candidate is `{freeze['candidate_name']}`. Model family remains smooth viscous plus dry friction. No production or training profile was edited, and no model was exported.",'',"Validation8 and validation9 were previously inspected. They are regression holdouts in this experiment, not a novel blind validation. Both original batch-6 recordings were already development; training8 and training9 were newly authorized for fitting. All 66 annotated releases across six recordings remain in the evidence.",'',f"Frozen parameters: effective length {freeze['parameters']['effective_length_m']:.9f} m, viscous coefficient {freeze['parameters']['viscous_per_s']:.9f} /s, dry-friction coefficient {freeze['parameters']['coulomb_rad_per_s2']:.9f} rad/s², local raw-angle phase {freeze['parameters']['local_angle_offset_rad']:.9f} rad. This phase is an inference in the encoder coordinate, not global angle calibration.",'',"## Paired results",'',"RMS / P95 in degrees. Short forecasts use 0.5 s horizons and up to 0.2 s causal history. Continuous forecasts use one 0.25 s or 0.5 s history, exclude that history from errors, then receive no more measurements. The 0.5 s history is primary.",'',"| Recording | Baseline short | Candidate short | Baseline cont .5 | Candidate cont .5 | Baseline cont .25 | Candidate cont .25 |","| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for b,c in zip(baseline,candidate):text.append('| '+b['label']+' | '+' | '.join(fmt(r['metrics'][k]) for k in ['short','.5','.25'] for r in [b,c])+' |')
    for label,b,c in [('Regression pooled',bp,cp),('Latest four pooled',summary['latest4_pooled']['baseline'],summary['latest4_pooled']['candidate'])]:text.append('| **'+label+'** | '+' | '.join(fmt(r[k]) for k in ['short','.5','.25'] for r in [b,c])+' |')
    text+=['',"Pooled metrics use all individual prediction residuals, not averages of recording summaries. Both parameter and initializer candidates were evaluated on identical samples. Baseline latest-four scores reproduce the prior evidence within 1e-8 degree.",'',"## Selection and regression decision",'',"The method was written before fitting. Training selection used equal-recording mean continuous 0.5 s RMS, with fixed short, quarter-history, per-recording and gate-regression constraints. Candidate selection was frozen before this experiment loaded validation measurements. No alternative was chosen after regression scoring.",'',"| Candidate | Training mean short RMS | Training mean cont .5 RMS | Training mean cont .25 RMS | Eligible |","| --- | ---: | ---: | ---: | :---: |"]
    for x in tr['selection']:text.append(f"| {x['name']} | {x['equal_recording_rms']['short']:.3f} | {x['equal_recording_rms']['.5']:.3f} | {x['equal_recording_rms']['.25']:.3f} | {x['eligible']} |")
    text+=['',"Frozen regression criteria:",'']+[f"- `{k}`: **{v}**." for k,v in checks.items()]
    text+=['',"## Uncertainty and measurements",'',f"Regression camera screens pass {quality_counts['regression']['camera_pass']}/{quality_counts['regression']['releases']}; held poses pass {quality_counts['regression']['pose_pass']}/{quality_counts['regression']['releases']}. Across the latest four recordings these remain {quality_counts['latest4']['camera_pass']}/{quality_counts['latest4']['releases']} and {quality_counts['latest4']['pose_pass']}/{quality_counts['latest4']['releases']}. Every failed screen is preserved in `per-release.json` and marked on plots. Better prediction does not resolve those failures.",'',summary['uncertainty']['interpretation'],'',"| Metric | Candidate minus baseline RMS | Descriptive 95% bootstrap interval |","| --- | ---: | ---: |"]
    for k,u in summary['uncertainty']['metrics'].items():text.append(f"| {k} | {u['candidate_minus_baseline_rms_deg']:.3f}° | {u['paired_release_bootstrap_95pct_interval_deg'][0]:.3f}° to {u['paired_release_bootstrap_95pct_interval_deg'][1]:.3f}° |")
    text+=['',f"Across all six recordings, baseline/candidate short numeric passes are {gate_counts['baseline']['numeric_pass']}/{gate_counts['candidate']['numeric_pass']} of 66, and coverage passes are {gate_counts['baseline']['coverage_pass']}/{gate_counts['candidate']['coverage_pass']} of 66. Training6 release-09 is a preserved 1.356 s partial interval with only two short forecasts; its original three-window coverage gate remains failed. The initial scorer abort on this failure was corrected without changing the gate, annotations, fits, or selection method; original script and log are preserved in `coverage-correction.json`.",'',"The robust weak leave-one-recording-out parameter spread is in `training.json.gz`. This is a stability diagnostic, not a calibrated confidence interval. Full-trajectory fitting uses per-release initial states as training nuisance parameters only; evaluation always estimates state from causal history. Friction, phase, encoder distortion, release handling and residual cart motion can still be confounded. A passing pixel pivot screen cannot certify physical cart stationarity. Absolute angle calibration, driven-cart input gain/delay and hardware approval remain unresolved.",'',"## Every release",'',"Each numeric cell is RMS / P95 degrees. C/P denotes original camera free-interval and held-pose screens. Short numeric/coverage flags and all exact failure reasons are in `per-release.json`.",'',"| Recording / release | Baseline short | Candidate short | Baseline cont .5 | Candidate cont .5 | Baseline cont .25 | Candidate cont .25 | C/P |","| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |"]
    for r in per:text.append('| '+r['label']+'/'+r['episode_id']+' | '+' | '.join(fmt(r[m][k]) for k in ['short','.5','.25'] for m in ['baseline','candidate'])+' | '+('pass' if r['camera_quality']['passed'] else 'FAIL')+'/'+('pass' if r['camera_quality']['pose_verified'] else 'FAIL')+' |')
    text+=['',"## Reproduce",'',"Run from the repository root, using an output directory that does not contain prior outputs:",'','```bash','uv run --offline --script evidence/passive-refinement-20261017/tools/refine.py train --output /tmp/passive-refinement-repeat','uv run --offline --script evidence/passive-refinement-20261017/tools/refine.py regression --output /tmp/passive-refinement-repeat','uv run --offline --script evidence/passive-refinement-20261017/tools/verify_causality.py --output /tmp/passive-refinement-repeat/causality-verification.json','MPLCONFIGDIR=/tmp/passive-refinement-mpl uv run --offline --script evidence/passive-refinement-20261017/tools/report.py --evidence /tmp/passive-refinement-repeat','```','',"The scripts use preserved archives if ignored extracted recordings are absent. Online dependency installation may be needed on a new machine; the recorded run used cached environments only. Sources, annotations, original archive hashes and exact fit method hashes are recorded in the training and regression reports. Candidate freeze and baseline freeze hashes remain separate. All outputs are developmental evidence.",'',"Plots:",'']+[f"- [{s['label']} comparison]({s['label']}-comparison.png)" for s in sources]
    (out/'README.md').write_text('\n'.join(text)+'\n')
    causal=read(out/'causality-verification.json');assert causal['passed'] and causal['method_sha256']==sha(Path(__file__).with_name('refine.py'))
    print(json.dumps(summary,indent=2),flush=True)
    verification=dict(tool_hashes={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},causality=causal,passed=True,baseline_parity=parity,all_release_count=len(per),unchanged_annotation_and_archive_hashes=True,method_hashes_verified=True,freeze_precedes_regression=True,no_training_regression_source_overlap=True,no_skipped_releases=True,identical_prediction_samples=True,analytic_sensitivity_check=tr['preflight'],outputs={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['verification.json']})
    save(out/'verification.json',verification)
if __name__=='__main__':main()
