#!/usr/bin/env python3
"""Offline artifact audit only. No serial, camera, network, or device access."""
import argparse
import hashlib
import gzip
import json
import math
from pathlib import Path
import subprocess
import tarfile
import tempfile


def sha(data):return hashlib.sha256(data).hexdigest()


def decode(theta,reference=370,sign=1):
    if not math.isfinite(theta) or abs(theta)>math.pi+1e-6:raise ValueError('theta range')
    scaled=sign*theta*4096/math.tau
    delta=round(scaled)
    residual=abs(scaled-delta)
    if residual>.001:raise ValueError('not an audited native count encoding')
    return (reference+delta)%4096,residual


def timing_lower_bound(rows):
    """No interpolation: legacy fitter duration is a conservative lower bound.

    Every original timestamp must remain in dataset provenance, together with
    period_semantics='minimum observed spacing; not uniform sample period'.
    """
    if len(rows)<2:raise ValueError('need at least two source states')
    sid=rows[0]['sid']
    for i,row in enumerate(rows):
        if row['sid']!=sid:raise ValueError('session change')
        if row['mode']!=0 or row['fault']!=0 or row['flags']&258 or not row['flags']&1:
            raise ValueError('unhealthy, enabled, or calibrating source')
        if i:
            before=rows[i-1]
            if row['tick']<=before['tick'] or row['us']<=before['us']:
                raise ValueError('duplicate or rolled-back source acquisition')
            if row['received_ns']<before['received_ns']:raise ValueError('host receipt rollback')
    gaps=[b['us']-a['us'] for a,b in zip(rows,rows[1:])]
    return {'sample_period_s':min(gaps)/1e6,'lower_bound_duration_s':(len(rows)-1)*min(gaps)/1e6,
            'actual_elapsed_s':(rows[-1]['us']-rows[0]['us'])/1e6,
            'max_gap_us':max(gaps),'uniform':len(set(gaps))==1,
            'period_semantics':'minimum observed spacing; not uniform sample period'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--capture',help='optional existing SDK shadow capture; read-only diagnostic')
    args=parser.parse_args()
    archive=Path(args.release)
    paths=('firmware/teensy_executor/teensy_executor.ino','firmware/teensy_executor/encoder_reference.h',
           'firmware/teensy_executor/executor_core.h','artifacts/executor-v4-rehome.hex')
    with tarfile.open(archive) as tar:
        manifest=json.load(tar.extractfile('release-source-manifest.json'))
        files={name:tar.extractfile(name).read() for name in paths}
    assert all(sha(raw)==manifest[name] for name,raw in files.items())
    ino=files[paths[0]].decode()
    contracts={
      'identity':'executor-v4-rehome', 'sign':'#define ENC_INVERT      0',
      'unfiltered_theta':'th = theta_meas;  // telemetry retains the raw encoder angle',
      'raw_reads_each_tick':'    encUpdate();', 'raw_theta_updates_each_tick':'    estimate(encTheta());',
      'board_tick_timestamp':'executor_state.acquisition_us',
      'raw_age_is_change_age':'if(raw!=enc_last_raw)enc_raw_changed_us=micros();'}
    assert all(text in ino for text in contracts.values())
    cpp=r'''#include "encoder_reference.h"
#include <cstdio>
#include <clocale>
#include <limits>
int main(){
 static_assert(sizeof(float)==4 && std::numeric_limits<float>::is_iec559,"IEEE float32 required");
 std::setlocale(LC_ALL,"C");
 for(int ref: {0,370,4095})for(int inv=0;inv<2;++inv)for(int raw=0;raw<4096;++raw){
  float theta=encoder_reference::angle_from_upright(raw,inv!=0,ref);
  char wire[64];std::snprintf(wire,sizeof wire,"%.7g",double(theta));
  std::printf("%d %d %d %s\n",ref,inv,raw,wire);
 }
}'''
    cpp='#include <initializer_list>\n'+cpp
    with tempfile.TemporaryDirectory(prefix='state-raw-audit-') as directory:
        root=Path(directory);(root/'encoder_reference.h').write_bytes(files[paths[1]])
        (root/'audit.cpp').write_text(cpp)
        version=subprocess.check_output(['c++','--version'],text=True).splitlines()[0]
        subprocess.run(['c++','-std=c++17','-O2',str(root/'audit.cpp'),'-o',str(root/'audit')],check=True)
        output=subprocess.check_output([str(root/'audit')],text=True)
    worst=0.;live_worst=0.;count=0
    for line in output.splitlines():
        ref,inv,raw,wire=line.split();ref,inv,raw=map(int,(ref,inv,raw))
        recovered,residual=decode(float(wire),ref,-1 if inv else 1)
        assert recovered==raw,(line,recovered)
        worst=max(worst,residual);count+=1
        if ref==370 and inv==0:live_worst=max(live_worst,residual)
    # Explicit malformed/non-lattice values must not turn into invented counts.
    for bad in (float('nan'),float('inf'),.1,4.):
        try:decode(bad)
        except ValueError:pass
        else:raise AssertionError('bad theta accepted')
    # Irregular actual native samples: retain a dropped interval; never fill it.
    times=[i*10000+(10000 if i>=20 else 0) for i in range(41)]
    rows=[dict(sid=9,tick=i+1,us=t,received_ns=1_000_000_000+t*1000,flags=5,mode=0,fault=0) for i,t in enumerate(times)]
    timing=timing_lower_bound(rows)
    assert timing['actual_elapsed_s']==.41 and timing['lower_bound_duration_s']==.4
    for mutation in ('duplicate_tick','time_rollback','sid','health','enabled','fault','calibrating','host_rollback'):
        copied=[dict(r) for r in rows]
        if mutation=='duplicate_tick':copied[1]['tick']=copied[0]['tick']
        elif mutation=='time_rollback':copied[1]['us']=0
        elif mutation=='sid':copied[1]['sid']=10
        elif mutation=='health':copied[1]['flags']=4
        elif mutation=='enabled':copied[1]['flags']=7
        elif mutation=='fault':copied[1]['fault']=1
        elif mutation=='calibrating':copied[1]['flags']=261
        else:copied[1]['received_ns']=0
        try:timing_lower_bound(copied)
        except ValueError:pass
        else:raise AssertionError(mutation)
    result={'audit_version':'lossless-state-count-v1','release_tar_sha256':sha(archive.read_bytes()),
      'release_member_sha256':{k:sha(v) for k,v in files.items()},'release_manifest_matches':True,
      'compiler':version,'compile_flags':['-std=c++17','-O2'],'compiled_actual_archived_header':True,
      'state_printf_format':'%.7g','cases':count,'mismatches':0,
      'references_tested':[0,370,4095],'both_signs_tested':True,'live_reference':370,'live_encoder_invert':0,
      'max_integer_residual_counts':worst,'live_max_integer_residual_counts':live_worst,
      'recommended_residual_limit_counts':.001,'decode':'(370 + round(theta * 4096 / (2*pi))) modulo 4096',
      'provenance_label':'lossless raw-count decode from unfiltered STATE theta',
      'irregular_timing_test':timing,'rejected_condition_tests':8,'malformed_angle_tests':4,
      'source_contract_checks':contracts,
      'limitations':['Archived source/hex identity is manifest-verified; this audit is not an attestation of the bytes currently flashed.',
       'Distinct healthy control ticks imply distinct successful register reads under this firmware, not independent ADC conversions.',
       'Board timestamp is control-tick start, preceding the I2C transaction; host receipt is later and must be retained separately.',
       'INFO raw age measures time since value change, not time since successful read.',
       'No physical reference uncertainty, pose correctness, magnetic accuracy, or calibration approval is established.']}
    if args.capture:
        from cartpole_sdk.sensing.calibration import _window, CalibrationPolicy
        capture=Path(args.capture);states={};metadata_count=0
        with gzip.open(capture,'rt') as source:
            for line in source:
                row=json.loads(line)
                if row.get('type')!='encoder_batch':continue
                for packet in row['response']['packets']:
                    info=packet['sdk_info'];state=packet['sdk_state']
                    assert info['firmware']=='executor-v4-rehome' and info['encoder_upright_raw']==370
                    assert info['encoder_conf_valid'] is True and info['encoder_conf']&0x3F0F==0x0300
                    assert info['sid']==state['sid']
                    metadata_count+=1
                    key=(state['sid'],state['unwrapped_tick'])
                    if key in states:
                        assert states[key]['theta']==state['theta']
                    else:states[key]=state
        source_states=list(states.values())
        ledger=[dict(sid=r['sid'],tick=r['unwrapped_tick'],us=r['unwrapped_us'],
                     received_ns=r['received_ns'],mode=r['mode'],flags=r['flags'],fault=r['fault'],
                     theta=r['theta'],raw_counts=decode(r['theta'])[0]) for r in source_states]
        all_timing=timing_lower_bound(ledger)
        selected=ledger[:101];selected_timing=timing_lower_bound(selected)
        window=dict(window_id='diagnostic-existing-first101-no-physical-reference-claim',sampling='native',
                    raw_counts=[r['raw_counts'] for r in selected],sample_period_s=selected_timing['sample_period_s'])
        window_report=_window(window,4096,CalibrationPolicy())
        assert not window_report['issues']
        result['existing_capture_diagnostic']={
            'capture':str(capture),'compressed_sha256':sha(capture.read_bytes()),
            'unique_healthy_stopped_states':len(source_states),'metadata_verified_packets':metadata_count,
            'max_integer_residual_counts':max(decode(r['theta'])[1] for r in source_states),
            'all_timing':all_timing,'selected_window_timing':selected_timing,
            'selected_window_fitter_report':window_report,'selected_window_source_ledger':selected,
            'limitations':'Diagnostic window only: no paired upright, physical uncertainty, direction/session coverage or calibration approval is inferred.'}
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ('cases','mismatches','live_max_integer_residual_counts','recommended_residual_limit_counts')}))

if __name__=='__main__':main()
