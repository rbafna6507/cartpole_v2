const assert=require('node:assert/strict');
const {test}=require('node:test');
const {series}=require('../../src/cartpole_vision/sdk.js');
test('same-time SDK corrections replace previous fused angle, including invalidation',()=>{
 const row=(seq,value,validity='valid')=>({sequence:seq,host_t:1.1+seq/100,observation:{samples:[{quantity:'angle',source:'fused',effective_ns:1000000000,value,validity}]}});
 const result=series({samples:[row(1,.1),row(2,.2)]});
 assert.equal(result.fused.length,1);assert.equal(result.fused[0].theta_rad,.2);
 assert.equal(series({samples:[row(1,.1),row(2,null,'invalid')]}).fused[0].theta_rad,null);
});
