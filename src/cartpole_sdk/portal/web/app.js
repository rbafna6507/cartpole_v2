'use strict';
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('cartpole-token') || '';
let localCredentials = null, approvalJob = null, identity = null;
let jobs = [], reservations = [], config = {}, activeView = 'experiments';
let videoPlayer = null;
let cameraRunning = false, cameraTimer = null, cameraWatchdog = null, cameraGeneration = 0;
$('token').value = token;

async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { Authorization: 'Bearer ' + token, ...(body === undefined ? {} : {'Content-Type': 'application/json'}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return response;
}
async function api(path, body) { return (await request(path, body)).json(); }
function message(text) { $('message').textContent = text; }
function action(label, handler, quiet = true) {
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = label;
  if (quiet) button.className = 'quiet';
  button.onclick = handler;
  return button;
}
function showView(view) {
  if (!['experiments', 'live', 'data', 'reservations'].includes(view)) view = 'experiments';
  activeView = view;
  for (const panel of document.querySelectorAll('.view')) panel.hidden = panel.id !== 'view-' + view;
  for (const button of document.querySelectorAll('[data-view]')) {
    const selected = button.dataset.view === view;
    button.classList.toggle('active', selected);
    if (selected) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  }
  if (view !== 'live') pauseCamera();
  if (view === 'reservations' && token) refreshReservations();
}
for (const button of document.querySelectorAll('[data-view]')) button.onclick = () => { location.hash = button.dataset.view; };
window.addEventListener('hashchange', () => showView(location.hash.slice(1)));
showView(location.hash.slice(1));
$('access-toggle').onclick = () => { $('access-panel').open = true; $('access-panel').scrollIntoView({block: 'center'}); $('token').focus(); };

function runRow(job) {
  const row = document.createElement('article'); row.className = 'run';
  const title = document.createElement('div'); title.className = 'run-title';
  const filename = document.createElement('strong'); filename.textContent = job.filename;
  const status = document.createElement('span'); status.className = 'status'; status.dataset.state = job.status;
  status.textContent = job.status.replaceAll('_', ' ');
  title.append(filename, status);
  const detail = document.createElement('small');
  detail.textContent = `${job.duration} seconds · ${job.source === 'simulation' ? 'Simulation' : 'Physical rig'} · ${new Date(job.created * 1000).toLocaleString()}`;
  row.append(title, detail);
  return row;
}
function hasRecording(job) { return job.result?.recording?.status === 'available'; }
async function downloadRecording(job, button) {
  button.disabled = true;
  try {
    const response = await request('/api/jobs/' + encodeURIComponent(job.id) + '/recording');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = 'cartpole-run-' + job.id + '.zip';
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  } catch (error) { message(error.message); }
  finally { button.disabled = false; }
}
function downloadButton(job) {
  const button = action('Download bundle', () => downloadRecording(job, button));
  return button;
}
function renderJobs() {
  $('jobs').replaceChildren(); $('data-jobs').replaceChildren();
  $('run-count').textContent = String(jobs.length); $('empty').hidden = jobs.length > 0;
  $('data-empty').hidden = jobs.length > 0;
  for (const job of jobs) {
    const row = runRow(job), actions = document.createElement('div'); actions.className = 'run-actions';
    actions.append(action('View details', () => { $('result-body').textContent = JSON.stringify(job, null, 2); $('result').open = true; $('result').scrollIntoView({block: 'nearest'}); }));
    if (hasRecording(job)) actions.append(downloadButton(job));
    if (identity?.role === 'submit' && ['awaiting_approval', 'pending', 'claimed', 'running'].includes(job.status)) {
      const cancel = action(job.cancel_requested ? 'Stop requested' : 'Cancel run', async () => {
        cancel.disabled = true;
        try { await api('/api/jobs/' + job.id + '/cancel', {}); await refresh(); }
        catch (error) { message(error.message); cancel.disabled = false; }
      }); cancel.disabled = job.cancel_requested; actions.append(cancel);
    }
    if (identity?.role === 'operator' && job.status === 'awaiting_approval') {
      actions.append(action('Inspect source', async () => {
        try {
          const artifact = await api('/api/jobs/' + job.id + '/artifact');
          if (artifact.sha256 !== job.artifact) throw new Error('Artifact identity changed');
          const bytes = Uint8Array.from(atob(artifact.source_base64), c => c.charCodeAt(0));
          $('result-body').textContent = 'SHA-256: ' + artifact.sha256 + '\n\n' + new TextDecoder('utf-8', {fatal: true}).decode(bytes);
          $('result').open = true; $('result').scrollIntoView({block: 'nearest'});
        } catch (error) { message(error.message); }
      }), action('Approve physical run', () => openApproval(job), false));
    }
    row.append(actions); $('jobs').append(row);
    const dataRow = runRow(job), dataActions = document.createElement('div'); dataActions.className = 'run-actions';
    if (hasRecording(job)) dataActions.append(downloadButton(job));
    else { const note = document.createElement('small'); note.textContent = ['completed', 'failed', 'cancelled'].includes(job.status) ? 'No recorded bundle is attached to this run.' : 'Recording becomes available after execution.'; dataActions.append(note); }
    dataRow.append(dataActions); $('data-jobs').append(dataRow);
  }
}
async function refresh() {
  try {
    identity = await api('/api/me');
    const data = await api('/api/jobs'); jobs = data.jobs;
    $('submission').hidden = identity.role !== 'submit';
    $('operator-upload-note').hidden = identity.role === 'submit';
    $('connection').textContent = identity.role + ' · ' + identity.principal;
    document.body.classList.add('connected');
    $('access-panel').open = false;
    renderJobs(); message('');
    try {
      config = await api('/api/config');
      $('camera-source').textContent = config.camera_url || 'No camera source configured.';
      $('camera-start').disabled = !config.camera_url;
      await refreshReservations();
    } catch (error) {
      config = {}; $('camera-source').textContent = 'Camera configuration is unavailable. Restart the updated portal server.';
      $('camera-start').disabled = true;
      $('reservation-status').textContent = 'Reservation configuration is unavailable. Restart the updated portal server.';
      $('reservation-form').hidden = true;
    }
  } catch (error) { $('connection').textContent = 'Connection needs attention'; document.body.classList.remove('connected'); message(error.message); }
}
$('connect').onclick = () => { token = $('token').value.trim(); sessionStorage.setItem('cartpole-token', token); refresh(); };
$('forget').onclick = () => {
  pauseCamera(); localCredentials = null; identity = null; config = {}; jobs = []; reservations = [];
  $('credential-file').value = ''; $('dev-role').disabled = true; token = ''; $('token').value = '';
  sessionStorage.removeItem('cartpole-token'); renderJobs(); $('reservations').replaceChildren();
  $('connection').textContent = 'Not connected'; document.body.classList.remove('connected');
  $('result-body').textContent = 'Select a run to inspect its result.'; $('result').open = false;
  $('reservation-form').hidden = true; $('reservation-status').textContent = 'Connect to check reservation availability.';
  $('reservation-assignment').hidden = true; $('camera-source').textContent = 'Connect to load the camera configuration.';
  $('camera-start').disabled = true; $('submission').hidden = false; $('operator-upload-note').hidden = true;
  message(''); $('access-panel').open = true;
};
$('refresh').onclick = refresh; $('refresh-data').onclick = refresh;
$('file').onchange = () => { $('file-label').textContent = $('file').files[0]?.name || 'Choose a Python file'; };
$('source').onchange = updateReservationAssignment;
$('submission').onsubmit = async event => {
  event.preventDefault(); const file = $('file').files[0];
  if (!file || file.size > 65536 || !file.name.endsWith('.py')) { message('Choose one Python file up to 64 KiB.'); return; }
  $('upload').disabled = true;
  try {
    const body = {source: await file.text(), filename: file.name, sensor_source: $('source').value, duration: Number($('duration').value), idempotency_key: crypto.randomUUID()};
    if (body.sensor_source !== 'simulation' && $('run-reservation').value) body.reservation_id = $('run-reservation').value;
    await api('/api/jobs', body); await refresh(); message('Experiment queued.');
  } catch (error) { message(error.message); }
  finally { $('upload').disabled = false; }
};
function openApproval(job) {
  approvalJob = job; $('approval-detail').textContent = `${job.filename} · ${job.duration} seconds · ${job.source}\nSHA-256: ${job.artifact}`;
  $('approval-error').textContent = ''; $('approval-dialog').showModal();
}
$('approval-cancel').onclick = () => $('approval-dialog').close();
$('approval-dialog').addEventListener('close', () => { approvalJob = null; });
$('approval-confirm').onclick = async () => {
  if (!approvalJob) return; const job = approvalJob; $('approval-confirm').disabled = true;
  try { await api('/api/jobs/' + job.id + '/approve', {artifact: job.artifact, sensor_source: job.source, duration: job.duration}); $('approval-dialog').close(); await refresh(); }
  catch (error) { $('approval-error').textContent = error.message; }
  finally { $('approval-confirm').disabled = false; }
};
function connectLocalRole() {
  const selected = Object.entries(localCredentials || {}).find(([, principal]) => principal[1] === $('dev-role').value);
  if (!selected) { message('No credential for this role.'); return; }
  $('token').value = selected[0]; $('connect').click();
}
$('dev-role').onchange = connectLocalRole;
$('credential-file').onchange = async () => {
  const file = $('credential-file').files[0]; if (!file) return;
  try {
    if (file.size > 16384) throw new Error('Credential file is too large.');
    const data = JSON.parse(await file.text());
    if (!data || Array.isArray(data) || typeof data !== 'object' || Object.entries(data).length !== 2 || !['submit', 'operator'].every(role => Object.entries(data).some(([key, value]) => /^[0-9a-f]{64}$/.test(key) && Array.isArray(value) && value.length === 2 && value[1] === role))) throw new Error('Choose the local preview credentials.json file.');
    localCredentials = data; $('dev-role').disabled = false; connectLocalRole();
  } catch (error) { message(error.message); }
};

function pauseCamera() {
  videoPlayer?.stop(); $('camera-video').hidden = true;
  cameraRunning = false; cameraGeneration++; clearTimeout(cameraTimer); clearTimeout(cameraWatchdog);
  $('camera-preview').onload = null; $('camera-preview').onerror = null;
  $('camera-preview').removeAttribute('src'); $('camera-preview').hidden = true;
  $('camera-placeholder').hidden = false; $('camera-status').textContent = 'Camera paused';
}
function cameraFrame(generation) {
  if (!cameraRunning || generation !== cameraGeneration || activeView !== 'live' || document.hidden) return;
  const image = $('camera-preview');
  const failed = () => {
    if (generation !== cameraGeneration) return;
    clearTimeout(cameraWatchdog); image.hidden = true; $('camera-placeholder').hidden = false;
    $('camera-status').textContent = 'Camera unavailable';
    $('camera-error').textContent = 'Cannot reach the camera preview. Check the camera service, tunnel, and configured source.';
    cameraTimer = setTimeout(() => cameraFrame(generation), 3000);
  };
  image.onload = () => {
    if (generation !== cameraGeneration) return;
    clearTimeout(cameraWatchdog); image.hidden = false; $('camera-placeholder').hidden = true;
    $('camera-status').textContent = 'Sampled JPEG preview';
    cameraTimer = setTimeout(() => cameraFrame(generation), 250);
  };
  image.onerror = failed;
  const url = new URL(config.camera_url); url.pathname = url.pathname.replace(/\/$/, '') + '/preview.jpg'; url.search = '?t=' + Date.now(); url.hash = '';
  cameraWatchdog = setTimeout(failed, 5000); image.src = url.href;
}
$('camera-start').onclick = () => {
  pauseCamera();
  try {
    const url = new URL(config.camera_url);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('A valid camera service URL must be configured by the operator.');
    cameraRunning = true; $('camera-error').textContent = '';
    if (!videoPlayer) videoPlayer = new PortalVideo($('camera-video'), {
      status: status => { $('camera-status').textContent = status; $('camera-video').hidden = true; $('camera-placeholder').hidden = false; },
      frame: () => { $('camera-video').hidden = false; $('camera-preview').hidden = true; $('camera-placeholder').hidden = true; $('camera-status').textContent = 'Live video'; $('camera-error').textContent = ''; },
      fallback: reason => { if (!cameraRunning) return; $('camera-video').hidden = true; $('camera-error').textContent = reason; if (location.protocol === 'https:' && new URL(config.camera_url).protocol !== 'https:') { $('camera-error').textContent += ' JPEG fallback requires an HTTPS camera source.'; return; } cameraFrame(cameraGeneration); },
    });
    videoPlayer.start(token);
  } catch (error) { $('camera-error').textContent = error.message; }
};
$('camera-stop').onclick = pauseCamera;
document.addEventListener('visibilitychange', () => { if (document.hidden) pauseCamera(); });

function updateReservationAssignment() {
  const select = $('run-reservation'), selected = select.value;
  select.replaceChildren(new Option('No reservation', ''));
  for (const reservation of reservations) {
    if (reservation.owner === identity?.principal && reservation.status !== 'cancelled' && reservation.ends_at > Date.now() / 1000) select.add(new Option(new Date(reservation.starts_at * 1000).toLocaleString(), reservation.id));
  }
  if ([...select.options].some(option => option.value === selected)) select.value = selected;
  $('reservation-assignment').hidden = !config.reservations_enabled || $('source').value === 'simulation';
}
async function refreshReservations() {
  try {
    const data = await api('/api/reservations'); reservations = data.reservations;
    $('reservation-form').hidden = !data.enabled || identity?.role !== 'submit';
    $('reservation-status').textContent = !data.enabled ? 'Reservations are not enabled on this deployment. You can still submit individual runs.' : identity?.role !== 'submit' ? 'Reservations are enabled. Use a submitter credential to reserve a session.' : 'Reserve a 30-minute window. Overlapping sessions are not available.';
    $('reservations').replaceChildren();
    for (const reservation of reservations) {
      const row = document.createElement('article'); row.className = 'run';
      const title = document.createElement('strong'); title.textContent = new Date(reservation.starts_at * 1000).toLocaleString();
      const details = document.createElement('small'); details.textContent = `${Math.round((reservation.ends_at - reservation.starts_at) / 60)} minutes · ${reservation.status} · ${reservation.owner}`;
      row.append(title, details);
      if (reservation.status !== 'cancelled' && reservation.ends_at > Date.now() / 1000 && (identity?.role === 'submit' && reservation.owner === identity?.principal)) {
        const actions = document.createElement('div'); actions.className = 'run-actions';
        actions.append(action('Cancel reservation', async () => { try { await api('/api/reservations/' + reservation.id + '/cancel', {}); await refreshReservations(); } catch (error) { $('reservation-message').textContent = error.message; } })); row.append(actions);
      }
      $('reservations').append(row);
    }
    if (!reservations.length) { const empty = document.createElement('p'); empty.className = 'muted'; empty.textContent = 'No sessions reserved yet.'; $('reservations').append(empty); }
    updateReservationAssignment();
  } catch (error) { $('reservation-status').textContent = error.message; $('reservation-form').hidden = true; }
}
$('refresh-reservations').onclick = refreshReservations;
const nextStart = new Date(Date.now() + 60000); nextStart.setSeconds(0, 0);
$('reservation-start').value = new Date(nextStart.getTime() - nextStart.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
$('reservation-form').onsubmit = async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {
    await api('/api/reservations', {rig: config.rig_id || 'cartpole', starts_at: new Date($('reservation-start').value).getTime() / 1000, duration_minutes: Number($('reservation-minutes').value)});
    $('reservation-message').textContent = 'Session reserved.'; await refreshReservations();
  } catch (error) { $('reservation-message').textContent = error.message; }
  finally { button.disabled = false; }
};
fetch('/api/dev-info').then(response => response.ok ? response.json() : null).then(info => {
  if (info?.local_preview === true && ['127.0.0.1', 'localhost'].includes(location.hostname)) {
    $('dev-preview').hidden = false; $('dev-access').hidden = false; $('environment').textContent = 'Local development';
  }
}).catch(() => {});
$('camera-start').disabled = true;
if (token) refresh();
