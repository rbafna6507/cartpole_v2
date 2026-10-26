const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/cartpole_sdk/portal/web/app.js'), 'utf8');
function setup(fetch) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {value: '', hidden: false, disabled: false,
      options: id === 'camera-mode' ? ['camera','overlay','mask'].map(value => ({value})) : [],
      classList: {add(){},remove(){},toggle(){}}, addEventListener(){}, removeAttribute(){},
      replaceChildren(){}, append(){}, scrollIntoView(){}, focus(){}, click(){this.onclick();},
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    window: {CARTPOLE_CONFIG: {apiOrigin: 'https://rig.example.test', hosted:true}, addEventListener(){}},
    document: {getElementById:element, querySelectorAll(){return [];}, addEventListener(){}, body:element('body'), hidden:false},
    location: {hash:'#live', origin:'https://portal.example.test', hostname:'portal.example.test', protocol:'https:'},
    sessionStorage: {getItem(){return null;},setItem(){},removeItem(){}}, fetch,
    URL, AbortController, Blob, setTimeout, clearTimeout, Date, Uint8Array, TextDecoder, btoa, atob,
    PortalVideo: class {constructor(canvas, callbacks){this.callbacks=callbacks;} stop(){} start(token,url){this.url=url;this.callbacks.fallback('JPEG fallback');}},
  });
  vm.runInContext(source, context);
  vm.runInContext("token = 'test-token'; config = {camera_url:'/api/video', camera_available:true};", context);
  return {context, element};
}
test('JPEG fallback uses authenticated API origin and selected mask without direct camera URL', async () => {
  const calls = [];
  const h = setup(async (url, options) => { calls.push({url, options}); return {ok:true, blob:async () => new Blob(['jpeg'])}; });
  h.element('camera-mode').value = 'mask';
  h.element('camera-start').onclick();
  await new Promise(resolve => setImmediate(resolve));
  try {
    assert.equal(calls[0].url, 'https://rig.example.test/api/camera/preview?mode=mask');
    assert.equal(calls[0].options.headers.Authorization, 'Bearer test-token');
    assert.equal(calls[0].options.redirect, 'error');
    assert.match(h.element('camera-preview').src, /^blob:/);
  } finally { h.context.pauseCamera(); }
});
test('presentation selector posts only mode then reflects current shared camera mode', async () => {
  const calls = [];
  const h = setup(async (url, options) => { calls.push({url, options}); return {ok:true, json:async () => ({mode:'overlay',modes:['camera','overlay','mask']})}; });
  h.element('camera-mode').value = 'overlay';
  await h.element('camera-mode').onchange();
  assert.equal(calls[0].url, 'https://rig.example.test/api/camera/mode');
  assert.deepEqual(JSON.parse(calls[0].options.body), {mode:'overlay'});
  assert.equal(calls[1].url, 'https://rig.example.test/api/camera');
  assert.equal(h.element('camera-mode').value, 'overlay');
  assert.equal(h.element('camera-mode').disabled, false);
});

test('opening Live view starts connected camera automatically without restarting an active stream', async () => {
  const calls = [];
  const h = setup(async (url, options) => { calls.push({url, options}); return {ok:true, blob:async () => new Blob(['jpeg'])}; });
  vm.runInContext("identity = {role:'submit'};", h.context);
  try {
    h.context.showView('live');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls.length, 1);
    h.context.showView('live');
    assert.equal(calls.length, 1);
    h.context.showView('experiments');
    assert.equal(vm.runInContext('cameraRunning', h.context), false);
  } finally { h.context.pauseCamera(); }
});


test('Python uploads preserve source; ZIP and actor uploads preserve exact bytes as base64', async () => {
  const h = setup(async () => { throw Error('unexpected network request'); });
  const python = {name:'controller.py',size:19,text:async () => '# a controller\n'};
  const source = await h.context.submissionArtifact(python);
  assert.equal(source.source, '# a controller\n');
  assert.equal(source.artifact_base64, undefined);
  for (const name of ['project.zip','actor.json']) {
    const bytes = Uint8Array.from([0,255,128,80,75,10]);
    const payload = await h.context.submissionArtifact({name,size:bytes.length,arrayBuffer:async () => bytes.buffer});
    assert.deepEqual(Buffer.from(payload.artifact_base64, 'base64'), Buffer.from(bytes));
    assert.equal(payload.source, undefined);
  }
});
test('upload bounds reject unsupported, empty, and oversized artifacts before reading', async () => {
  const h = setup(async () => { throw Error('unexpected network request'); });
  const invalid = [undefined, {name:'policy.pkl',size:20}, {name:'empty.py',size:0},
    {name:'big.py',size:65537}, {name:'big.zip',size:8*1024*1024+1}, {name:'big.json',size:1000001}];
  for (const file of invalid) await assert.rejects(() => h.context.submissionArtifact(file));
});
test('ZIP inspection displays manifest without decoding binary archive contents', () => {
  const h = setup(async () => { throw Error('unexpected network request'); });
  const job = {filename:'project.zip'}, artifact = {sha256:'abc',inspection:{entrypoint:'policy.py',files:[{path:'policy.py',size:42}]}};
  const text = h.context.artifactInspection(job, artifact, Uint8Array.from([255,128,0]));
  assert.match(text, /Python project: project.zip/);
  assert.match(text, /policy.py/);
  assert.match(text, /SHA-256: abc/);
  assert.doesNotMatch(text, /�/);
});


test('hosted sign-in file accepts one submitter credential and rejects worker access', async () => {
  const calls=[];
  const h=setup(async (url, options) => { calls.push({url,options}); return {ok:false,json:async()=>({error:'test boundary'})}; });
  const key='a'.repeat(64);
  h.element('dev-role').value='operator';
  h.element('credential-file').files=[{size:100,text:async()=>JSON.stringify({[key]:['owner','submit']})}];
  await h.element('credential-file').onchange();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls[0]?.options.headers.Authorization,'Bearer '+key);
  assert.equal(h.element('dev-role').value,'submit');
  calls.length=0;
  h.element('credential-file').files=[{size:100,text:async()=>JSON.stringify({[key]:['worker','worker']})}];
  await h.element('credential-file').onchange();
  assert.equal(calls.length,0);
  assert.match(h.element('message').textContent,/sign-in file/i);
});

test('hosted page exposes sign-in file outside local development preview', () => {
  const html=fs.readFileSync(path.join(__dirname,'../../src/cartpole_sdk/portal/web/index.html'),'utf8');
  assert.match(html,/Sign in with file/);
  assert.doesNotMatch(html,/id="dev-access"[^>]*hidden/);
});


test('JPEG fallback gives a slow public relay a bounded 15 second transfer window', async () => {
  const h=setup(async()=>new Promise(()=>{}));
  const delays=[];
  h.context.setTimeout=(fn,delay)=>{delays.push(delay);return 1;};
  h.element('camera-start').onclick();
  assert.ok(delays.includes(15000));
  h.context.pauseCamera();
});

test('recording negotiation omits unsupported field for legacy backend', async () => {
  const calls=[];
  const h=setup(async(url,options)=>{calls.push({url,options});return {ok:false,json:async()=>({error:'stop after submit'})};});
  h.context.crypto={randomUUID:()=> 'stable-test-id'};
  h.element('file').files=[{name:'p.py',size:3,text:async()=> 'x=1'}];
  h.element('source').value='simulation';h.element('duration').value='1';h.element('recording').value='detailed';
  await h.element('submission').onsubmit({preventDefault(){}});
  assert.equal(Object.hasOwn(JSON.parse(calls[0].options.body),'recording'),false);
  calls.length=0;
  vm.runInContext("config.recording_modes=['standard','detailed'];",h.context);
  await h.element('submission').onsubmit({preventDefault(){}});
  assert.equal(JSON.parse(calls[0].options.body).recording,'detailed');
});
