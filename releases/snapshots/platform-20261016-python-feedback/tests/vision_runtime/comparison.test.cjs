const test=require('node:test'),assert=require('node:assert/strict');
const {ComparisonStore,angleLayers,Visibility}=require('../../src/cartpole_vision/comparison.js');
test('native encoder samples survive a vision outage and incremental repeats',()=>{
 const s=new ComparisonStore();
 const packet={epoch:'a',reset:true,last_seq:2,encoder:{samples:[{seq:1,t:1,theta_rad:.1},{seq:2,t:1.01,theta_rad:.2}]},fused:{samples:[]}};
 s.merge(packet);s.merge({...packet,reset:false});
 assert.equal(s.encoder.length,2);
 assert.equal(angleLayers([],s,{vision:true,encoder:true,fused:true})[1].points.length,2);
});
test('wrap crossing shares a branch between encoder and vision without erasing their difference',()=>{
 const s=new ComparisonStore();s.merge({epoch:'a',reset:true,last_seq:2,encoder:{samples:[{seq:1,t:1,theta_rad:3.13},{seq:2,t:1.01,theta_rad:-3.13}]},fused:{samples:[]}});
 const layers=angleLayers([{seq:1,t:1,theta_rad:-3.14},{seq:2,t:1.01,theta_rad:-3.12}],s,{vision:true,encoder:true,fused:true});
 assert.ok(Math.abs(layers[0].points[0].v-layers[1].points[0].v)<2);
 assert.ok(Math.abs(layers[1].points[1].v-layers[1].points[0].v)<2);
 assert.notEqual(layers[0].points[0].v,layers[1].points[0].v);
});
test('visibility persists and does not delete sensor history',()=>{
 let value=null;const storage={getItem:()=>value,setItem:(k,v)=>value=v};
 let v=new Visibility(storage);assert.equal(v.enabled.encoder,true);
 v.set('encoder',false);v=new Visibility(storage);assert.equal(v.enabled.encoder,false);
 const layers=angleLayers([],new ComparisonStore(),v.enabled);
 assert.equal(layers[1].visible,false);
});
test('long outage is not joined and stale histories expire',()=>{
 const s=new ComparisonStore();s.merge({epoch:'a',reset:true,last_seq:2,encoder:{samples:[{seq:1,t:1,theta_rad:.1},{seq:2,t:2,theta_rad:.2}]},fused:{samples:[]}});
 const layers=angleLayers([],s,{encoder:true});
 assert.equal(layers[1].segments.length,0);
 s.trim(20);assert.equal(s.encoder.length,0);
});
test('measured camera delay shifts blue samples onto the common timeline',()=>{
 const s=new ComparisonStore();
 s.merge({epoch:'a',reset:true,last_seq:0,status:{vision_delay_ms:25},encoder:{samples:[]},fused:{samples:[]}});
 const layers=angleLayers([{seq:1,t:1,theta_rad:.2}],s,{vision:true});
 assert.equal(layers[0].points[0].t,.975);
});
test('skipped camera frames remain visible as dashed gaps',()=>{
 const layers=angleLayers([{seq:10,t:1,theta_rad:.1},{seq:14,t:1.05,theta_rad:.2}],new ComparisonStore(),{vision:true});
 assert.equal(layers[0].segments[0].dashed,true);
});
