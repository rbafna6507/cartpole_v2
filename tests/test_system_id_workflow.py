"""Operator workflow: independent sources, immutable artifacts and scoped models."""
from dataclasses import asdict
import hashlib,json,math
from pathlib import Path
import numpy as np
import pytest
from cartpole_sdk.sim.config import SimulationConfig


def modules():
    from cartpole_sdk.identification import passive,workflow
    return passive,workflow


def episodes(run,amplitudes=(.35,-.4,.5,-.6,.7,-.75),length=.18):
    result=[];h=.00025
    for i,initial in enumerate(amplitudes):
        t=np.arange(0,3.004,.004);q,w=initial,0.;values=[q]
        def acc(q,w):return -9.81/length*math.sin(q)-.65*w
        for _ in range(len(t)-1):
            for __ in range(16):
                qm=q+h*w/2;wm=w+h*acc(q,w)/2;q+=h*wm;w+=h*acc(qm,wm)
            values.append(q)
        result.append(dict(run_id=run,episode_id=str(i),t_s=t.tolist(),theta_rad=(np.array(values)+math.pi-.09).tolist()))
    return result


def raw_recording(path,run,amplitudes=(.35,-.4,.5,-.6,.7,-.75),length=.18):
    data=episodes(str(run),amplitudes,length);records=[dict(type='session',session=dict(session_id=str(run),clock_id=f'board:{run}')),
        dict(type='info',info=dict(sid=run,firmware='executor-v6-measuredrail',encoder_upright_raw=100,
            home_epoch=2,reference_saved=True,encoder_conf_valid=True))]
    intervals=[]
    for i,ep in enumerate(data):
        begin=i*4
        intervals.append(dict(episode_id=str(i),board_relative_s=[begin,begin+3.],reason='hand clear; cart restrained'))
        for t,q in zip(ep['t_s'],ep['theta_rad']):
            tick=round((begin+t)*1000)
            records.append(dict(type='state',state=dict(sid=run,unwrapped_us=tick*1000,unwrapped_tick=tick,
                tick=tick,us=tick*1000,received_ns=(10_000+tick)*1_000_000,theta=q,angle_hat=q,omega=0.,x=0.,
                velocity=0.,acceleration=0.,flags=205,fault=0,mode=0,misses=0,dropped=0)))
    path.write_text(''.join(json.dumps(r)+'\n' for r in records))
    annotation=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),selected_before_scoring=True,
        operator_cart_restraint='operator held cart base fixed',selection_method='video hand-clear annotations',episodes=intervals)
    ap=path.with_suffix('.annotations.json');ap.write_text(json.dumps(annotation));return ap


def test_passive_math_recovers_independent_dynamics_and_validation_cannot_refit():
    passive,_=modules();train=episodes('training');valid=episodes('validation',(.42,-.55,.65,-.7))
    good=passive.fit_passive(train,valid,model='viscous')
    bad=passive.fit_passive(train,episodes('different',(.42,-.55,.65,-.7),.32),model='viscous')
    assert good['parameters']['effective_length_m']==pytest.approx(.18,abs=.002)
    assert good['parameters']['angular_damping_per_s']==pytest.approx(.65,abs=.04)
    assert good['statistical_checks_pass'] and not bad['statistical_checks_pass']
    assert good['parameters']==bad['parameters']
    with pytest.raises(ValueError,match='independent'):passive.fit_passive(train,train,model='viscous')


def test_raw_logs_explicit_annotations_and_per_episode_validation(tmp_path):
    _,flow=modules();train=tmp_path/'train.jsonl';valid=tmp_path/'valid.jsonl'
    ta=raw_recording(train,7);va=raw_recording(valid,8,(.42,-.55,.65,-.7))
    report=flow.fit_passive_logs(train,ta,valid,va,model='viscous')
    assert report['accepted'] and report['acceptance_scope']=='passive-down-conditional'
    assert len(report['per_episode_validation'])==4
    assert report['provenance']['training']['sha256']!=report['provenance']['validation']['sha256']
    assert report['physical_cart_stationarity_certified'] is False
    assert report['recommended_for_hardware_rl'] is False
    assert report['camera_evidence']['status']=='not supplied'


def test_copy_renaming_hash_reuse_and_annotation_mismatch_reject(tmp_path):
    _,flow=modules();a=tmp_path/'a.jsonl';b=tmp_path/'copy.jsonl';ann=raw_recording(a,7);b.write_bytes(a.read_bytes())
    with pytest.raises(ValueError,match='independent'):flow.fit_passive_logs(a,ann,b,ann)
    annotation=json.loads(ann.read_text());annotation['source_sha256']='0'*64;ann.write_text(json.dumps(annotation))
    with pytest.raises(ValueError,match='hash'):flow.passive_episodes(a,ann)

@pytest.mark.parametrize('problem',('overlap','unfrozen','unrestrained','reversed','duplicate_conflict','enabled','reference'))
def test_annotation_clock_and_disabled_source_guards(tmp_path,problem):
    _,flow=modules();p=tmp_path/'a.jsonl';ap=raw_recording(p,7);annotation=json.loads(ap.read_text())
    rows=[json.loads(line) for line in p.read_text().splitlines()]
    if problem=='overlap':annotation['episodes'][1]['board_relative_s']=[2,5]
    if problem=='unfrozen':annotation['selected_before_scoring']=False
    if problem=='unrestrained':annotation['operator_cart_restraint']=''
    if problem=='reversed':rows[4]['state']['unwrapped_us']=0
    if problem=='duplicate_conflict':
        import copy
        duplicate=copy.deepcopy(rows[3]);duplicate['state']['x']=.001;rows.insert(4,duplicate)
    if problem=='enabled':rows[5]['state']['flags']=207
    if problem=='reference':rows[1]['info']['reference_saved']=False
    p.write_text(''.join(json.dumps(r)+'\n' for r in rows));annotation['source_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();ap.write_text(json.dumps(annotation))
    with pytest.raises(ValueError):flow.passive_episodes(p,ap)


def test_static_heldout_rejects_even_with_zero_forecast_error():
    passive,_=modules();train=episodes('train');t=np.arange(0,12,.004).tolist()
    valid=[dict(run_id='static',episode_id='0',t_s=t,theta_rad=[math.pi-.09]*len(t))]
    report=passive.fit_passive(train,valid,model='viscous')
    assert not report['statistical_checks_pass']
    assert 'insufficient heldout angle excitation' in report['reasons']


def test_immutable_output_rejected_export_and_explicit_mapping(tmp_path):
    _,flow=modules();out=tmp_path/'model.json'
    base=asdict(SimulationConfig());assumptions=dict(simulation_config=base,rationale='Masses and force authority remain explicitly assumed.')
    report=dict(accepted=False,kind='passive',model='viscous',parameters={},reasons=['bad validation'])
    with pytest.raises(ValueError,match='accepted'):flow.export_model(report,scope='passive-down',assumptions=assumptions,output=out)
    assert not out.exists()
    report.update(accepted=True,acceptance_scope='passive-down-conditional',parameters=dict(effective_length_m=.18,
        angular_damping_per_s=.65,coulomb_rad_per_s2=0.,angle_offset_rad=-.09))
    model=flow.export_model(report,scope='passive-down',assumptions=assumptions,output=out)
    cfg=model['simulation_config'];assert cfg['effective_length_m']==.18
    assert cfg['hinge_damping']==pytest.approx(.65*.75*.02275*.18**2)
    assert {k:v for k,v in cfg.items() if k not in ('effective_length_m','hinge_damping')}=={k:v for k,v in base.items() if k not in ('effective_length_m','hinge_damping')}
    assert model['local_angle_comparison']['offset_applied_to_simulator'] is False
    assert model['recommended_for_hardware_rl'] is False
    assert flow.load_model(out).effective_length_m==.18
    old=out.read_bytes()
    with pytest.raises(FileExistsError):flow.export_model(report,scope='passive-down',assumptions=assumptions,output=out)
    assert out.read_bytes()==old


def test_export_cannot_drop_unsupported_friction_or_actuator_dynamics(tmp_path):
    _,flow=modules();base=dict(simulation_config=asdict(SimulationConfig()),rationale='explicit assumptions')
    for kind,parameters in [('passive',dict(coulomb_rad_per_s2=.4)),('driven',dict(input_gain=1.5,delay_s=.01))]:
        report=dict(accepted=True,kind=kind,model='viscous',acceptance_scope='passive-down-conditional' if kind=='passive' else 'driven-conditional',
            parameters=dict(effective_length_m=.18,angular_damping_per_s=.6,**parameters))
        with pytest.raises(ValueError,match='represent'):flow.export_model(report,scope='passive-down' if kind=='passive' else 'driven',assumptions=base,output=tmp_path/(kind+'.json'))


def test_identical_status_retransmission_is_deduplicated_without_rewriting_source(tmp_path):
    _,flow=modules();path=tmp_path/'a.jsonl';ap=raw_recording(path,7)
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    import copy
    duplicate=copy.deepcopy(rows[3]);duplicate['state']['received_ns']+=100
    rows.insert(4,duplicate);path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    pin=hashlib.sha256(path.read_bytes()).hexdigest();a=json.loads(ap.read_text());a['source_sha256']=pin;ap.write_text(json.dumps(a))
    episodes,identity=flow.passive_episodes(path,ap)
    assert identity['duplicate_snapshots']==1 and identity['sha256']==pin
    assert hashlib.sha256(path.read_bytes()).hexdigest()==pin
    assert len(episodes[0]['t_s'])==751


@pytest.mark.parametrize('format',('plain','gzip','tar'))
def test_input_bounds_are_enforced_before_unbounded_allocation(tmp_path,format):
    import gzip,io,tarfile
    _,flow=modules();raw=b'{"n":1}\n'*20;path=tmp_path/'input.jsonl'
    if format=='plain':path.write_bytes(raw);spec=path
    elif format=='gzip':path=path.with_suffix('.gz');path.write_bytes(gzip.compress(raw));spec=path
    else:
        path=path.with_suffix('.tar.gz')
        with tarfile.open(path,'w:gz') as archive:
            entry=tarfile.TarInfo('run/source.jsonl');entry.size=len(raw);archive.addfile(entry,io.BytesIO(raw))
        spec=str(path)+'::run/source.jsonl'
    with pytest.raises(ValueError,match='byte'):flow.load_records(spec,max_bytes=40)
    with pytest.raises(ValueError,match='line'):flow.load_records(spec,max_line_bytes=4)
    with pytest.raises(ValueError,match='record'):flow.load_records(spec,max_records=3)
    records,identity=flow.load_records(spec,max_bytes=len(raw),max_line_bytes=8,max_records=20)
    assert len(records)==20 and identity['sha256']==hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('bad',({'type':'termination','error':None,'records_dropped':1},
    {'type':'termination','error':'transport failed','records_dropped':0},
    {'type':'stop_failure','reason':'unconfirmed'}, {'type':'passive_failure','reason':'camera failed'}))
def test_failure_records_are_rejected_including_historical_sources(tmp_path,bad):
    _,flow=modules();path=tmp_path/'input.jsonl';ann=raw_recording(path,7)
    with path.open('a') as stream:stream.write(json.dumps(bad)+'\n')
    annotation=json.loads(ann.read_text());annotation['source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();ann.write_text(json.dumps(annotation))
    with pytest.raises(ValueError,match='fail|lost'):flow.passive_episodes(path,ann)


def collection_source(tmp_path):
    _,flow=modules();path=tmp_path/'rig-test.jsonl';ann=raw_recording(path,7)
    with path.open('a') as stream:stream.write(json.dumps({'type':'passive_start','seconds':120})+'\n')
    pin=hashlib.sha256(path.read_bytes()).hexdigest();annotation=json.loads(ann.read_text());annotation['source_sha256']=pin;ann.write_text(json.dumps(annotation))
    report=dict(schema='cartpole-id-run-v1',raw_log=path.name,raw_log_sha256=pin,completed=True,stop_confirmed=True,records_dropped=0,camera={})
    return path,ann,report


@pytest.mark.parametrize('problem',('missing','wrong_hash','incomplete','camera_failure','dropped','unconfirmed_stop','wrong_name','failure'))
def test_new_collections_require_bound_successful_completion_report(tmp_path,problem):
    _,flow=modules();path,ann,report=collection_source(tmp_path)
    if problem=='wrong_hash':report['raw_log_sha256']='0'*64
    elif problem=='incomplete':report['completed']=False
    elif problem=='camera_failure':report['camera']['failure']='camera timed out after logger closed'
    elif problem=='dropped':report['records_dropped']=1
    elif problem=='unconfirmed_stop':report['stop_confirmed']=False
    elif problem=='wrong_name':report['raw_log']='unrelated.jsonl'
    elif problem=='failure':report['failure']='operator interrupted'
    if problem!='missing':(tmp_path/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='collection|report'):flow.passive_episodes(path,ann)


def test_archived_collection_report_is_bound_without_extraction(tmp_path):
    import gzip,io,tarfile
    _,flow=modules();path,ann,report=collection_source(tmp_path);raw=path.read_bytes()
    archive_path=tmp_path/'run.tar.gz'
    with tarfile.open(archive_path,'w:gz') as archive:
        for name,payload in [('nested/'+path.name,raw),('nested/report.json',json.dumps(report).encode())]:
            entry=tarfile.TarInfo(name);entry.size=len(payload);archive.addfile(entry,io.BytesIO(payload))
    episodes,identity=flow.passive_episodes(str(archive_path)+'::nested/'+path.name,ann)
    assert len(episodes)==6 and identity['collection_report']['completed'] is True
    assert identity['collection_report']['sha256']==hashlib.sha256(json.dumps(report).encode()).hexdigest()
    gz=tmp_path/(path.name+'.gz');gz.write_bytes(gzip.compress(raw));(tmp_path/'report.json').write_text(json.dumps(report))
    assert len(flow.passive_episodes(gz,ann)[0])==6


def test_same_session_cannot_be_disguised_by_other_metadata(tmp_path):
    _,flow=modules();a=tmp_path/'a.jsonl';b=tmp_path/'b.jsonl';aa=raw_recording(a,7);ba=raw_recording(b,7,(.4,-.5,.6))
    rows=[json.loads(line) for line in b.read_text().splitlines()];rows[0]['session']['extra']='copy renamed'
    b.write_text(''.join(json.dumps(row)+'\n' for row in rows));annotation=json.loads(ba.read_text());annotation['source_sha256']=hashlib.sha256(b.read_bytes()).hexdigest();ba.write_text(json.dumps(annotation))
    with pytest.raises(ValueError,match='independent'):flow.fit_passive_logs(a,aa,b,ba)
