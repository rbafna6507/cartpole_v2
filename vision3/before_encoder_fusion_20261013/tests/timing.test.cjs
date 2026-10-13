const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const file=path.join(__dirname,'../pendulum_vision/timing.js');
test('clock probe bounds and source-to-canvas age use the same clock',()=>{
  assert.ok(fs.existsSync(file));
  const {clockSample,frameAge}=require(file);
  const sample=clockSample(1000,1020,5);
  assert.equal(sample.offset_ms,-3990);
  assert.equal(sample.uncertainty_ms,10);
  const age=frameAge(4.5,500000,1110,sample);
  assert.equal(age.estimate_ms,100);
  assert.equal(age.lower_ms,90);
  assert.equal(age.upper_ms,110);
});
test('missing origin and expired probes cannot report a latency',()=>{
  assert.ok(fs.existsSync(file));
  const {clockSample,frameAge}=require(file);
  const sample=clockSample(1000,1020,5);
  assert.equal(frameAge(null,0,1110,sample),null);
  assert.equal(frameAge(5,0,32000,sample),null);
});
