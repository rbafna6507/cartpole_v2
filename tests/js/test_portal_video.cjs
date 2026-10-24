const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/cartpole_sdk/portal/web/video.js'), 'utf8');
function setup(fetch, clock = performance) {
  const decoded = [], fallbacks = [], timers = [], closed = [], intervals = [];
  let number = 0;
  class Decoder {
    constructor(callbacks) { this.callbacks = callbacks; this.state = 'configured'; this.decodeQueueSize = 0; }
    configure() {}
    decode(chunk) { decoded.push(chunk); this.callbacks.output({displayWidth: 8, displayHeight: 8, close() {closed.push('frame');}}); }
    close() { this.state = 'closed'; }
  }
  const sandbox = {window: {}, VideoDecoder: Decoder, EncodedVideoChunk: class {constructor(data) {Object.assign(this,data);}},
    AbortController, performance: clock, Uint8Array, DataView, fetch,
    setTimeout(fn, delay) {timers.push({fn, delay}); return ++number;}, clearTimeout() {}, setInterval(fn) {intervals.push(fn); return ++number;}, clearInterval() {},
    requestAnimationFrame() {return ++number;}, cancelAnimationFrame() {},};
  sandbox.window.VideoDecoder = Decoder; sandbox.window.EncodedVideoChunk = sandbox.EncodedVideoChunk;
  vm.runInNewContext(source, sandbox);
  const canvas = {getContext() {return {clearRect() {}, drawImage() {}};}};
  const player = new sandbox.window.PortalVideo(canvas, {fallback: value => fallbacks.push(value)});
  return {player, decoded, fallbacks, timers, closed, intervals};
}
function packet(key, timestamp, data = [1,2,3]) {
  const bytes = new Uint8Array(13 + data.length), header = new DataView(bytes.buffer);
  header.setUint32(0, data.length); header.setBigUint64(4, BigInt(timestamp)); header.setUint8(12, key ? 1 : 0); bytes.set(data,13); return bytes;
}
function response(parts) {return {ok: true, body: {getReader() {return {async read() {return parts.length ? {value:parts.shift(),done:false}:{done:true};},async cancel(){}};}}};}
test('fragmented packets decode only from a keyframe and reconnect on stream end', async () => {
  const packets = Buffer.concat([packet(false,0),packet(true,10000),packet(false,20000)]);
  const h = setup(async () => response([packets.subarray(0,7),packets.subarray(7,21),packets.subarray(21)]));
  await h.player.connect(h.player.generation);
  assert.equal(h.decoded.length,2); assert.equal(h.decoded[0].type,'key'); assert.equal(h.decoded[1].type,'delta');
  assert.equal(h.fallbacks.length,0); assert.equal(h.timers.at(-1).delay,750);
});
test('oversized packet fails closed and selects explicit JPEG fallback', async () => {
  const bytes = packet(true,0); new DataView(bytes.buffer).setUint32(0,9*1024*1024);
  const h = setup(async () => response([bytes])); await h.player.connect(h.player.generation);
  assert.equal(h.decoded.length,0); assert.match(h.fallbacks[0],/Invalid video packet size/);
});
test('late network response after stop cannot decode or request reconnect', async () => {
  let resolve; const h = setup(() => new Promise(done => {resolve=done;}));
  const connected = h.player.connect(h.player.generation); h.player.stop();
  let cancelled = false; resolve({ok:true,body:{async cancel(){cancelled=true;},getReader(){throw Error('stale reader must not be used');}}});
  await connected; assert.equal(cancelled,true); assert.equal(h.decoded.length,0); assert.equal(h.fallbacks.length,0); assert.equal(h.timers.length,0);
});
test('hosted video uses configured endpoint with authorization and disallows redirects', async () => {
  let call;
  const h = setup(async (url, options) => { call = {url, options}; return response([]); });
  h.player.token = 'test-token'; h.player.url = 'https://rig.example.test/api/video';
  await h.player.connect(h.player.generation);
  assert.equal(call.url, 'https://rig.example.test/api/video');
  assert.equal(call.options.headers.Authorization, 'Bearer test-token');
  assert.equal(call.options.redirect, 'error');
});
test('stalled stream cancellation cannot block JPEG fallback', async () => {
  const h = setup(async () => ({ok:true,body:{getReader(){return {
    async read(){throw Error('network stalled');},
    cancel(){return new Promise(() => {});}
  };}}}));
  const connected = h.player.connect(h.player.generation);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.fallbacks.length,1);
  assert.match(h.fallbacks[0],/network stalled/);
  await connected;
});

test('watchdog falls back even when a browser read ignores abort', async () => {
  let now = 0;
  const h = setup(async () => ({ok:true,body:{getReader(){return {
    read(){return new Promise(() => {});}, cancel(){return new Promise(() => {});}
  };}}}), {now:()=>now});
  void h.player.connect(h.player.generation);
  await new Promise(resolve => setImmediate(resolve));
  now=8001; h.intervals[0]();
  assert.equal(h.fallbacks.length,1);
  assert.match(h.fallbacks[0],/No video frames/);
});
