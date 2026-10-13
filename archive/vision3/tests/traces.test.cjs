const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const file = path.join(__dirname, '../pendulum_vision/traces.js');
function api(){assert.ok(fs.existsSync(file), 'measurement trace module missing');return require(file);}
const row=(seq,t,angle)=>({seq,t,theta_rad:angle==null?null:angle*Math.PI/180});

test('angle crossing +/-180 remains continuous while raw measurements are unchanged',()=>{
  const {buildSeries}=api();const rows=[row(1,0,179),row(2,.0125,-179),row(3,.025,-177)];
  const result=buildSeries(rows,'theta_rad',{angular:true,scale:180/Math.PI});
  assert.deepEqual(result.points.map(p=>Math.round(p.v)),[179,181,183]);
  assert.equal(result.segments.length,2);
  assert.equal(result.segments[0].bridged,false);
  assert.ok(rows[1].theta_rad<0);
});
test('single valid points remain visible and short missing runs are dashed only',()=>{
  const {buildSeries}=api();
  const result=buildSeries([row(1,0,170),row(2,.0125,null),row(3,.025,172)],'theta_rad',{angular:true});
  assert.equal(result.points.length,2);assert.equal(result.segments.length,1);
  assert.equal(result.segments[0].bridged,true);
  assert.equal(buildSeries([row(1,0,170)],'theta_rad').points.length,1);
});
test('long gaps and ambiguous large angle changes are not bridged',()=>{
  const {buildSeries}=api();
  assert.equal(buildSeries([row(1,0,170),row(30,.5,-170)],'theta_rad',{angular:true}).segments.length,0);
  assert.equal(buildSeries([row(1,0,10),row(3,.1,170)],'theta_rad',{angular:true}).segments.length,0);
});
test('skipped capture frames are marked as gaps even if both endpoints are valid',()=>{
  const {buildSeries}=api();
  const result=buildSeries([row(1,0,10),row(4,.0375,12)],'theta_rad',{angular:true});
  assert.equal(result.segments[0].bridged,true);
});
test('history batches deduplicate, expire, and clear on calibration/session changes',()=>{
  const {HistoryStore}=api();const store=new HistoryStore();
  store.merge({epoch:'one',reset:true,last_seq:2,samples:[row(1,0,1),row(2,.01,2)]});
  store.merge({epoch:'one',reset:false,last_seq:3,samples:[row(2,.01,2),row(3,.02,3)]});
  assert.deepEqual(store.rows.map(r=>r.seq),[1,2,3]);assert.equal(store.after,3);
  store.merge({epoch:'one',reset:false,last_seq:4,samples:[row(4,20,4)]});
  assert.deepEqual(store.rows.map(r=>r.seq),[4]);
  store.merge({epoch:'two',reset:true,last_seq:1,samples:[row(1,0,5)]});
  assert.deepEqual(store.rows.map(r=>r.seq),[1]);assert.equal(store.epoch,'two');
});
test('null cart values stay absent and real cart positions retain their scale',()=>{
  const {buildSeries}=api();
  const result=buildSeries([{seq:1,t:0,cart_x_m:null},{seq:2,t:.01,cart_x_m:.012}], 'cart_x_m',{scale:1000});
  assert.equal(result.points.length,1);assert.equal(result.points[0].v,12);
  assert.equal(result.segments.length,0);
});
test('angle branch stays fixed when the rolling buffer drops its oldest anchor',()=>{
  const {HistoryStore,buildSeries}=api(),store=new HistoryStore();
  store.merge({epoch:'one',reset:true,samples:[row(1,0,179),row(2,.0125,-179)]});
  const later=Array.from({length:1200},(_,i)=>row(i+3,(i+2)/80,-177));
  store.merge({epoch:'one',reset:false,samples:later});
  const series=buildSeries(store.rows,'theta_rad',{angular:true,scale:180/Math.PI});
  assert.equal(store.rows[0].seq,2);
  assert.equal(Math.round(series.points[0].v),181);
  assert.equal(Math.round(series.points.at(-1).v),183);
});
test('a camera stall is dashed even if sequence numbers are consecutive',()=>{
  const {buildSeries}=api();
  assert.equal(buildSeries([row(1,0,170),row(2,.24,172)],'theta_rad',{angular:true}).segments[0].bridged,true);
  assert.equal(buildSeries([row(1,0,170),row(2,.1,172)],'theta_rad',{angular:true}).segments[0].bridged,false);
});
