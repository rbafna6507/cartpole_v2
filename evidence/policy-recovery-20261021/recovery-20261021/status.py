#!/usr/bin/env python3
"""Read recovery progress over HTTP without queuing work in the busy training kernel."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import time
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('recovery_watch',HERE/'watch.py')
wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
w=wrapper.watch

def status():
    pins=json.loads((HERE.parent/'combined-next/http-checkpoint-cli-pins.json').read_text())
    for name,expected in pins['files'].items():
        if w.digest(w.ROOT/name)!=expected:raise ValueError('pinned download implementation changed')
    def download(remote,destination):
        w.download_cli(w.ROOT/pins['executable'],Path.home()/'.config/colab-cli/sessions.json',w.SESSION,
                       w.REMOTE_ROOT+remote,destination,45)
    with tempfile.TemporaryDirectory(prefix='cartpole-recovery-status-') as folder:
        folder=Path(folder);jobfile=folder/'job.json'
        download('job-status.json',jobfile);job=json.loads(jobfile.read_text())
        run=job.get('run')
        if run not in w.RUNS:raise ValueError('unexpected training run')
        reportfile=folder/'report.json';download(run+'/report.json',reportfile)
        report=json.loads(reportfile.read_text())
        if report['protocol_sha256']!=w.EXPECTED_PROTOCOL:raise ValueError('report protocol mismatch')
        progress=None;progressfile=folder/'progress.csv'
        try:
            download(run+'/logs/progress.csv',progressfile)
            for row in csv.DictReader(progressfile.open()):
                if None not in row and all(v is not None for v in row.values()) and row.get('time/total_timesteps'):
                    progress={k:row[k] for k in ('time/total_timesteps','time/fps','train/n_updates') if k in row}
        except w.DownloadError:pass
        return dict(session=w.SESSION,recorded_status=job['status'],run=run,
            latest_saved_step=max(c['step'] for c in report['checkpoints']),latest_progress=progress,
            completed_trials=len(job.get('completed_trials',[])),optimizer_resume=report.get('optimizer_resume'),
            checked_at_unix=time.time(),note='Fresh HTTP file observation; progress advancement establishes work. No live-process or kernel query.',
            evaluations=report.get('evaluations',[]))

if __name__=='__main__':
    try:print(json.dumps(status(),indent=2))
    except (ValueError,OSError,w.DownloadError) as error:raise SystemExit('Training status unavailable: '+str(error))
