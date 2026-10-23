const {test} = require('node:test');
const assert = require('node:assert/strict');
const {mkdtemp, readFile, readdir, rm} = require('node:fs/promises');
const {tmpdir} = require('node:os');
const {join} = require('node:path');
const modulePath = '../../deployment/vercel/build.mjs';
test('hosted build includes only public assets and exact API origin CSP', async () => {
  const {build} = await import(modulePath);
  const output = await mkdtemp(join(tmpdir(), 'cartpole-vercel-test-'));
  try {
    await build('https://rig.example.test/', output);
    assert.deepEqual((await readdir(join(output, 'static'))).sort(), ['app.js','config.js','index.html','style.css','video.js']);
    const config = await readFile(join(output, 'static/config.js'), 'utf8');
    assert.match(config, /"apiOrigin":"https:\/\/rig.example.test"/);
    assert.match(config, /"hosted":true/);
    const headers = JSON.parse(await readFile(join(output, 'config.json'))).routes[0].headers;
    assert.match(headers['Content-Security-Policy'], /connect-src 'self' https:\/\/rig.example.test;/);
    assert.doesNotMatch(headers['Content-Security-Policy'], /\*|unsafe-inline|unsafe-eval/);
    const html = await readFile(join(output, 'static/index.html'), 'utf8');
    assert.ok(html.indexOf('/config.js') < html.indexOf('/app.js'));
  } finally { await rm(output, {recursive:true, force:true}); }
});
test('hosted build rejects unsafe and non-origin endpoints', async () => {
  const {apiOrigin} = await import(modulePath);
  for (const value of [undefined, '', 'http://rig.example.test', 'https://token@rig.example.test', 'https://rig.example.test/api', 'https://rig.example.test?token=x', 'https://rig.example.test#x', 'https://localhost', 'https://127.0.0.1']) assert.throws(() => apiOrigin(value));
  assert.equal(apiOrigin('https://rig.example.test:8443/'), 'https://rig.example.test:8443');
});
