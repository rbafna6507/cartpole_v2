#!/usr/bin/env python3
"""Teensy characterization: guided pendulum and cart collection, plus offline analysis.
Run `python lab.py --help`. Only the explicit drive command sends bounded cart targets after guided homing.
"""
import argparse,csv,json,time,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from analysis import (FIELDS,write_json,circular_raw,delta_raw,stationary,analyze,export_model)

DEFAULT_CONFIG=Path(__file__).with_name('equipment.json')

def stamp():return datetime.now().strftime('%Y%m%d_%H%M%S_%f')

def ports():
    from serial.tools import list_ports
    return list(list_ports.comports())

def choose_port(requested):
    if requested:return requested
    ps=ports()
    # Never silently choose one board among several.
    if len(ps)==1:return ps[0].device
    raise ValueError('Specify --port. Available ports: '+', '.join(p.device for p in ps))

class Recorder:
    def __init__(self,port,baud=115200,serial_instance=None):
        if serial_instance is None:
            import serial
            self.ser=serial.Serial(choose_port(port),baud,timeout=.1,write_timeout=1)
        else:self.ser=serial_instance
        self.info=[];deadline=time.monotonic()+5;sent=0
        while time.monotonic()<deadline:
            if time.monotonic()-sent>.5:self.send('INFO');sent=time.monotonic()
            line=self.ser.readline().decode('ascii','replace').strip()
            if line.startswith('I '):
                self.info.append(line)
                if 'protocol=3' in line:break
        else:
            self.ser.close();raise ValueError('No protocol=3 reply. Upload teensy_pendulum_characterization.ino, select USB Serial on Teensy, and close other serial monitors.')
    def send(self,command):
        if hasattr(self,'active_meta') and command!='PING':
            self.active_meta['host_commands'].append(dict(command=command,host_send_monotonic_ns=time.monotonic_ns()))
        self.ser.write((command+'\n').encode('ascii'))
    def close(self):
        try:self.send('STOP')
        finally:self.ser.close()
    def collect(self,prefix,command='STREAM',duration=2.,metadata=None,tick=None):
        prefix=Path(prefix);prefix.parent.mkdir(parents=True,exist_ok=True)
        meta=dict(created_utc=datetime.now(timezone.utc).isoformat(),board=self.info,command=command,
            events=[],host_stop_reason=None,malformed_rows=0,metadata=metadata or {},data_csv=prefix.name+'.csv',host_commands=[])
        csvpath=Path(str(prefix)+'.csv');metapath=Path(str(prefix)+'_capture.json')
        if csvpath.exists():raise ValueError('Capture already exists: '+str(csvpath))
        write_json(metapath,meta)
        start=time.monotonic();ping=start;stop_at=None;first_t=None;ack=False;rows=0;latest=None
        with csvpath.open('x',newline='') as f,Path(str(prefix)+'_protocol.log').open('x') as log:
            writer=csv.writer(f);writer.writerow(FIELDS+['host_monotonic_ns'])
            self.active_meta=meta
            self.send(command)
            try:
                while True:
                    now=time.monotonic()
                    if now-ping>=.1:self.send('PING');ping=now
                    if not ack and now-start>4:raise ValueError('Board did not acknowledge capture')
                    if ack and tick is not None and stop_at is None:
                        tick(self,now-start,latest,meta)
                    timed_out=(now-start>130) if duration is None else (now-start>duration and ack)
                    if timed_out and stop_at is None:
                        self.send('STOP');stop_at=now;meta['host_stop_reason']='duration' if duration is not None else 'timeout'
                    if stop_at is not None and now-stop_at>2:meta['host_stop_reason']='missing_END';break
                    line=self.ser.readline().decode('ascii','replace').strip();arrival=time.monotonic_ns()
                    if not line:continue
                    log.write(f'{arrival} {line}\n')
                    if line.startswith('I '):self.info.append(line)
                    elif line.startswith('E '):
                        parts=line.split()
                        if len(parts)>=3:
                            ev=dict(t_us=int(parts[1]),name=parts[2],detail=' '.join(parts[3:]),host_monotonic_ns=arrival)
                            meta['events'].append(ev)
                            if parts[2] in ('ARMED','STREAM'):ack=True
                            if parts[2]=='HELD_release_now':print('  Stable hold detected. Release now without a push.',flush=True)
                            if parts[2].startswith('RELEASE'):print('  Release detected; collecting decay...',flush=True)
                            if parts[2]=='END' and ack:break
                            if parts[2].startswith('ERROR'):raise ValueError(line)
                    elif line.startswith('D ') and ack:
                        parts=line[2:].split(',')
                        if len(parts)!=len(FIELDS):meta['malformed_rows']+=1;continue
                        try:
                            vals=[float(v) for v in parts]
                            sample_t=int(parts[1])
                        except ValueError:meta['malformed_rows']+=1;continue
                        if first_t is None:first_t=sample_t
                        latest=dict(zip(FIELDS,vals));writer.writerow(parts+[arrival]);rows+=1
                        if rows%250==0:f.flush();log.flush()
            except KeyboardInterrupt:
                meta['host_stop_reason']='keyboard_interrupt';print('\nCapture interrupted; raw data retained.')
            finally:
                try:self.send('STOP')
                except OSError:meta['host_stop_reason']='serial_disconnected'
                meta['rows']=rows;meta['first_sample_t_us']=first_t
                # Only board timestamps establish release relative to the CSV.
                releases=[e for e in meta['events'] if e['name'].startswith('RELEASE')]
                meta['release_s']=(releases[0]['t_us']-first_t)*1e-6 if releases and first_t is not None else None
                write_json(metapath,meta)
        print('  Saved',csvpath)
        return csvpath,meta


def equipment(path):return json.loads(Path(path).read_text())

def capture_metadata(args):
    return dict(equipment=equipment(args.config),operator_note=getattr(args,'note',''))

def zero_capture(rec,folder,meta):
    input('Let the arm hang freely at DOWN, wait until still, then press Enter: ')
    path,_=rec.collect(folder/'down_reference',duration=3,metadata=meta)
    result=stationary(path);write_json(folder/'down_reference_metrics.json',result)
    print(f"  Stationary angle std: {result['angle_std_deg']:.3f}°, span: {result['angle_peak_to_peak_deg']:.3f}°")
    if result['angle_peak_to_peak_deg']>1:raise ValueError('Down-reference moved by >1 degree; repeat when still')
    return result['zero_raw']

def static_calibration(rec,args,folder):
    meta=capture_metadata(args);zero=zero_capture(rec,folder,meta)
    # Visit each target from both directions to expose hysteresis/loose coupling.
    targets=[0,15,30,60,90,60,30,15,0,-15,-30,-60,-90,-60,-30,-15,0]
    results=[]
    for i,angle in enumerate(targets):
        input(f'Hold the arm at PHYSICAL {angle:+g} degrees (protractor; + toward your chosen positive side), then Enter: ')
        path,_=rec.collect(folder/f'angle_{i:02d}',duration=2,metadata=dict(meta,known_angle_deg=angle,order=i))
        s=stationary(path)
        results.append(dict(angle_deg=angle,raw_mean=s['zero_raw'],std_deg=s['angle_std_deg'],span_deg=s['angle_peak_to_peak_deg'],csv=path.name))
        write_json(folder/'static_samples.json',results)
    x=np.array([float(delta_raw(r['raw_mean'],zero)) for r in results]);a=np.deg2rad([r['angle_deg'] for r in results])
    slope,intercept=np.polyfit(x,a,1);sign=1 if slope>0 else -1
    ideal=sign*x*2*np.pi/4096
    nodes=[];hysteresis={}
    for angle in sorted(set(targets)):
        subset=x[np.array(targets)==angle]
        nodes.append([float(np.mean(subset)),float(np.deg2rad(angle))])
        hysteresis[str(angle)]=float(np.ptp(subset)*360/4096)
    nodes.sort();angles=np.array(nodes)[:,1]
    monotonic=bool(np.all(np.diff(angles)*sign>0))
    stable=all(r['span_deg']<1 for r in results)
    result=dict(zero_raw=zero,sign=sign,linear_scale_relative_to_nominal=abs(slope)/(2*np.pi/4096),
        raw_angle_error_rms_deg=float(np.rad2deg(np.sqrt(np.mean((ideal-a)**2)))),
        linear_fit_error_rms_deg=float(np.rad2deg(np.sqrt(np.mean((slope*x+intercept-a)**2)))),
        directional_repeatability_span_deg=hysteresis,monotonic=monotonic,stable_samples=stable,
        nodes_raw_delta_angle_rad=nodes,samples=results,
        note='Piecewise-linear mapping over measured range only. Not automatically applied; pass --calibration explicitly. Approach repeatability includes operator/protractor error.')
    write_json(folder/'static_report.json',result)
    if monotonic and stable:write_json(folder/'encoder_calibration.json',result);print('Calibration saved. Inspect static_report.json before applying it.')
    else:print('Calibration rejected: nonmonotonic targets or unstable holds. Raw samples and report saved.')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,2,figsize=(10,4));ax[0].plot(np.rad2deg(a),np.rad2deg(ideal),'o');ax[0].plot([-90,90],[-90,90],'--');ax[0].set(xlabel='Known physical angle (deg)',ylabel='Raw encoder angle (deg)')
    ax[1].plot(np.rad2deg(a),np.rad2deg(ideal-a),'o');ax[1].set(xlabel='Known physical angle (deg)',ylabel='Raw angle error (deg)');fig.tight_layout();fig.savefig(folder/'static_plot.png',dpi=150);plt.close(fig)

def run_swing(rec,args,folder):
    if not args.cart_fixed:
        reply=input('Is the cart mechanically fixed and all swingup/balance control OFF? Type yes: ')
        if reply.strip().lower()!='yes':raise ValueError('Free-decay fitting requires a fixed cart with control off')
    meta=capture_metadata(args);meta.update(cart_fixed_operator_confirmed=True,nominal_release_angle_deg=args.angle)
    zero=zero_capture(rec,folder,meta)
    input(f'Place the arm at about {args.angle:+g} degrees and HOLD it there. While holding, press Enter: ')
    print('Keep holding until “Release now” appears. Then let go and do not touch the arm.')
    path,cap=rec.collect(folder/'swing',command='ARM',duration=None,metadata=dict(meta,zero_raw=zero))
    if cap['release_s'] is None:print('No release event. Data retained; repeat or analyze with an explicitly reviewed --release-s.');return
    cal=json.loads(Path(args.calibration).read_text()) if args.calibration else None
    metrics=analyze(path,release_s=cap['release_s'],zero_raw=zero,calibration=cal,fit=args.fit)
    print_summary(metrics)

def print_summary(m):
    print(json.dumps({k:m[k] for k in ('small_angle_period_estimate_s','positive_peak_count','negative_peak_count','warnings','dynamics_fit','fit_error') if k in m},indent=2))

def summarize(folder):
    rows=[]
    for path in sorted(Path(folder).rglob('*_lab_metrics.json')):
        m=json.loads(path.read_text());q=m['quality'];f=m.get('dynamics_fit',{})
        rows.append(dict(file=str(path),period_s=m.get('small_angle_period_estimate_s'),
            peak_deg=m.get('peak_recorded_angle_deg'),w0=f.get('w0_rad_s'),beta=f.get('beta_per_s'),gamma=f.get('gamma_rad_s2'),
            fit_rms_deg=f.get('fit_rms_deg'),growing_opposite_peaks=len(m.get('opposite_side_growth_events',[])),
            sample_hz=q.get('sample_rate_hz'),sequence_gaps=q.get('sequence_gaps'),warnings='; '.join(m.get('warnings',[]))))
    if not rows:raise ValueError('No *_lab_metrics.json files found; analyze swings first')
    out=Path(folder)/'session_summary.csv'
    with out.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_json(Path(folder)/'session_summary.json',dict(runs=rows,note='Do not average incompatible hardware, angle mappings, or moving-pivot trials. Compare left/right and different release amplitudes separately.'))
    print(out)


def manual_home_prompts():
    print('Drivers will be disabled. Support/secure the rail: ENABLE is shared with both Z motors.')
    input('With motors OFF, mark the left and right usable cart-centre endpoints with a ruler. Leave clearance from mechanical impacts. Enter when marked: ')
    span=float(input('Measured distance between those two marks, in mm: '))
    if not 100<=span<=600:raise ValueError('Supported measured span is 100–600 mm')
    input('Mark the midpoint. Move the cart manually to that midpoint. Leave the pendulum hanging; remove any cart clamp. Enter when centred and clear: ')
    return span

def run_drive(rec,args,folder):
    rec.send('OFF')
    span=manual_home_prompts()
    if not 1<=args.speed<=250 or not 10<=args.accel<=2000 or not 100<=args.jerk<=20000:raise ValueError('Limits out of supported characterization range')
    if not 1<=abs(args.distance)<=50 or abs(args.distance)>span/2-30:raise ValueError('Distance must be 1–50 mm and at least 30 mm inside each end')
    if not 1<=args.repeats<=5:raise ValueError('Repeats must be 1–5')
    if input('The shared drivers will energize and the cart will move. Type MOVE to start: ').strip()!='MOVE':raise ValueError('Cancelled')
    targets=[args.distance] if args.single else [v for _ in range(args.repeats) for v in (args.distance,0,-args.distance,0)]
    plan=dict(span_mm=span,targets_mm=targets,speed_mm_s=args.speed,accel_mm_s2=args.accel,jerk_mm_s3=args.jerk,
              measured_position_source='none; pulse-derived command only',manual_centre_operator_confirmed=True)
    write_json(folder/'plan.json',plan)
    stage='limits';sent=False;current=0;done_at=None;seen=0;finished=False;fault=None
    def tick(connection,elapsed,latest,meta):
        nonlocal stage,sent,current,done_at,seen,finished,fault
        if not sent:
            connection.send(f'LIMITS {args.speed} {args.accel} {args.jerk}');sent=True
        for ev in meta['events'][seen:]:
            name=ev['name']
            if name.startswith(('ERROR','FAULT')):
                fault=name+' '+ev['detail'];connection.send('STOP');finished=True;stage='failed'
            elif name=='LIMITS' and stage=='limits':connection.send(f'HOME {span}');stage='home'
            elif name=='HOME' and stage=='home':stage='ready';done_at=elapsed+.5
            elif name=='MOVE_DONE' and stage=='moving':
                if int(ev['detail'].split()[0])!=current:raise ValueError('Unexpected motion ID')
                stage='ready';done_at=elapsed+2 # record pendulum ringdown between targets
        seen=len(meta['events'])
        if stage=='ready' and elapsed>=done_at:
            if current<len(targets):
                connection.send(f'MOVE {current+1} {targets[current]}');current+=1;stage='moving'
            else:finished=True;stage='done';connection.send('STOP')
    budget=5+len(targets)*22
    # Collector's duration is an outer bound; firmware independently limits each move to 20 s.
    path,cap=rec.collect(folder/'drive',duration=budget,metadata=dict(capture_metadata(args),experiment='drive',plan=plan),tick=tick)
    complete=finished and fault is None and stage=='done'
    report=drive_report(path)
    report.update(completed=complete,fault=fault,plan=plan)
    if complete:
        prompt='Measured final displacement from your centre mark in mm (signed; Enter if unavailable): '
        measured=input(prompt).strip()
        report['measured_final_displacement_mm']=float(measured) if measured else None
        report['measurement_note']='Ruler endpoint after drivers disabled. Record only if cart remained at its stopped position.'
        report['expected_final_displacement_mm']=targets[-1]
    write_json(folder/'drive_report.json',report)
    print('Completed:',complete,'Saved:',folder)
    if fault:print('Fault:',fault,'Physically recenter and repeat homing before any further motion.')

def drive_report(path):
    from analysis import load_csv,quality
    d,t,valid=load_csv(path)
    if 'x_command_m' not in d.dtype.names:raise ValueError('No drive channels')
    result=dict(quality=quality(d,t,valid),max_abs_commanded_position_mm=float(np.max(abs(d['x_command_m']))*1000),
        max_abs_commanded_speed_mm_s=float(np.max(abs(d['v_command_m_s']))*1000),
        max_abs_commanded_acceleration_mm_s2=float(np.max(abs(d['a_command_m_s2']))*1000),
        warning='These are commanded/pulse-derived quantities, not observed motor tracking or physical acceleration.')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from analysis import delta_raw,circular_raw
    zero=circular_raw(d['raw'][valid][-min(1000,int(valid.sum())):])
    fig,ax=plt.subplots(3,1,figsize=(11,8),sharex=True);tr=t-t[0]
    ax[0].plot(tr,d['x_command_m']*1000);ax[0].set_ylabel('Pulse-derived x (mm)')
    ax[1].plot(tr,d['v_command_m_s']*1000);ax[1].set_ylabel('Command v (mm/s)')
    ax[2].plot(tr[valid],delta_raw(d['raw'][valid],zero)*360/4096);ax[2].set(ylabel='Encoder angle (deg)',xlabel='MCU time (s)')
    fig.suptitle('Driven experiment — cart position is not independently measured');fig.tight_layout();fig.savefig(Path(path).with_name('drive_plot.png'),dpi=150);plt.close(fig)
    return result

def run_timing(rec,args,folder):
    rec.send('OFF');rows=[]
    for i in range(args.count):
        before=time.monotonic_ns();rec.send(f'PING {i}');deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            line=rec.ser.readline().decode('ascii','replace').strip();after=time.monotonic_ns();parts=line.split()
            if len(parts)==4 and parts[0]=='E' and parts[2]=='PONG' and int(parts[3])==i:
                rows.append(dict(id=i,host_send_ns=before,host_receive_ns=after,board_receive_us=int(parts[1]),rtt_ms=(after-before)/1e6));break
        else:rows.append(dict(id=i,timeout=True))
    rtt=[r['rtt_ms'] for r in rows if 'rtt_ms' in r]
    report=dict(transport='USB serial',samples=rows,timeouts=len(rows)-len(rtt),
        median_ms=float(np.median(rtt)) if rtt else None,p95_ms=float(np.percentile(rtt,95)) if rtt else None,
        p99_ms=float(np.percentile(rtt,99)) if rtt else None,max_ms=max(rtt) if rtt else None,
        note='Host-to-firmware-to-host round-trip, including USB/Python buffering; not one-way delay, camera latency or motor response. Ethernet is not enabled in this build.')
    write_json(folder/'timing.json',report);print({k:v for k,v in report.items() if k!='samples'})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port');p.add_argument('--baud',type=int,default=115200)
    p.add_argument('--out',default='runs');p.add_argument('--config',default=str(DEFAULT_CONFIG))
    sub=p.add_subparsers(dest='cmd',required=True)
    summary=sub.add_parser('summary');summary.add_argument('folder')
    drive=sub.add_parser('drive',help='Guided manual centre reference and bounded cart experiment')
    drive.add_argument('--distance',type=float,default=20);drive.add_argument('--speed',type=float,default=30)
    drive.add_argument('--accel',type=float,default=300);drive.add_argument('--jerk',type=float,default=3000)
    drive.add_argument('--repeats',type=int,default=1);drive.add_argument('--single',action='store_true');drive.add_argument('--note',default='')
    timing=sub.add_parser('timing');timing.add_argument('--count',type=int,default=200)
    sub.add_parser('ports');sub.add_parser('measurements',help='Enter mass, COM and geometric measurements')
    sub.add_parser('static',help='Guided known-angle calibration and repeatability checks')
    noise=sub.add_parser('noise');noise.add_argument('--seconds',type=float,default=10)
    stream=sub.add_parser('stream',help='Timestamped recording only, no motor actuation');stream.add_argument('--seconds',type=float,default=20);stream.add_argument('--note',default='')
    s=sub.add_parser('swing');s.add_argument('--angle',type=float,required=True);s.add_argument('--cart-fixed',action='store_true');s.add_argument('--fit',action='store_true');s.add_argument('--calibration');s.add_argument('--note',default='')
    a=sub.add_parser('analyze');a.add_argument('csv');a.add_argument('--release-s',type=float);a.add_argument('--zero-raw',type=float);a.add_argument('--calibration');a.add_argument('--fit',action='store_true')
    e=sub.add_parser('export-model');e.add_argument('metrics');e.add_argument('--mass-g',type=float,required=True);e.add_argument('--com-mm',type=float,required=True);e.add_argument('--output',default='measured_model.json')
    d=sub.add_parser('displacement',help='Record a manually performed motor/ruler test; does not move the cart')
    d.add_argument('--pulses',type=int,required=True);d.add_argument('--measured-mm',type=float,required=True);d.add_argument('--seconds',type=float);d.add_argument('--note',default='')
    args=p.parse_args()
    if args.cmd=='summary':summarize(args.folder);return
    if args.cmd=='ports':
        for x in ports():print(x.device,x.description)
        return
    if args.cmd=='analyze':
        path=Path(args.csv);capture=path.with_name(path.stem+'_capture.json');cap=json.loads(capture.read_text()) if capture.exists() else {}
        release=args.release_s if args.release_s is not None else cap.get('release_s')
        zero=args.zero_raw if args.zero_raw is not None else cap.get('metadata',{}).get('zero_raw')
        cal=json.loads(Path(args.calibration).read_text()) if args.calibration else None
        print_summary(analyze(path,release,zero,cal,args.fit));return
    if args.cmd=='export-model':
        export_model(json.loads(Path(args.metrics).read_text()),args.mass_g/1000,args.com_mm/1000,args.output);print(args.output);return
    folder=Path(args.out)/(stamp()+'_'+args.cmd);folder.mkdir(parents=True,exist_ok=False)
    if args.cmd=='measurements':
        cfg=equipment(args.config);values={}
        for key,prompt in [('arm_mass_g','Bare arm mass (g)'),('tip_total_mass_g','COMBINED mass of both end weights (g)'),('total_rotating_mass_g','Complete rotating assembly mass, incl. hub/screws (g)'),('tip_distance_mm','Pivot to end-weight centre (mm)'),('com_mm','Pivot to measured balance point/COM (mm)'),('moving_cart_mass_g','Moving cart mass excluding pendulum (g)')]:
            value=input(prompt+' [Enter if unknown]: ').strip();values[key]=float(value) if value else None
            if values[key] is not None and values[key]<=0:raise ValueError('Measurements must be positive')
        write_json(folder/'measurements.json',dict(values=values,source_config=cfg));print(folder);return
    if args.cmd=='displacement':
        if args.pulses==0 or args.measured_mm==0:raise ValueError('Need nonzero signed pulses and measured displacement')
        if args.seconds is not None and args.seconds<=0:raise ValueError('Duration must be positive')
        cfg=equipment(args.config);h=cfg['hardware'];nominal=h['motor_full_steps_per_rev']*h['microsteps']/(h['pulley_teeth']*h['belt_pitch_mm'])
        scale=abs(args.pulses/args.measured_mm)
        write_json(folder/'displacement.json',dict(commanded_pulses=args.pulses,measured_displacement_mm=args.measured_mm,measured_steps_per_mm=scale,
            configured_steps_per_mm=nominal,scale_error_percent=100*(scale/nominal-1),same_direction=args.pulses*args.measured_mm>0,
            average_measured_speed_mm_s=args.measured_mm/args.seconds if args.seconds else None,note=args.note,
            limitation='Endpoint ruler test only. Does not identify acceleration, braking, torque or time-resolved tracking; missed steps cannot be ruled out.',equipment=cfg));print(folder);return
    rec=Recorder(args.port,args.baud)
    try:
        if args.cmd=='drive':run_drive(rec,args,folder)
        elif args.cmd=='timing':run_timing(rec,args,folder)
        elif args.cmd=='static':static_calibration(rec,args,folder)
        elif args.cmd=='swing':run_swing(rec,args,folder)
        else:
            if args.seconds<=0:raise ValueError('Duration must be positive')
            if args.cmd=='noise':input('Hold the pendulum completely stationary, then Enter: ')
            path,_=rec.collect(folder/args.cmd,duration=args.seconds,metadata=capture_metadata(args))
            if args.cmd=='noise':
                result=stationary(path);write_json(folder/'noise_metrics.json',result);print(json.dumps(result,indent=2))
    finally:rec.close()

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as e:sys.exit(str(e))
