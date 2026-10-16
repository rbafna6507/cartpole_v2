const assert=require('node:assert/strict');
const {test}=require('node:test');
const {waitDecodeCapacity}=require('../../src/cartpole_vision/timing.js');
test('bursty video yields to decoder without resetting valid queued frames',async()=>{
 let tick=0,yields=0;const decoder={decodeQueueSize:8,state:'configured'};
 await waitDecodeCapacity(decoder,new AbortController().signal,{now:()=>tick,yieldTurn:async()=>{tick+=4;yields++;decoder.decodeQueueSize--;}});
 assert.equal(yields,3);assert.equal(decoder.decodeQueueSize,5);
});
test('stuck decoder is bounded and abort does not consume more frames',async()=>{
 let tick=0;const decoder={decodeQueueSize:8,state:'configured'};
 await assert.rejects(waitDecodeCapacity(decoder,new AbortController().signal,{timeoutMs:10,now:()=>tick,yieldTurn:async()=>{tick+=4;}}),/decoder stalled/i);
 const controller=new AbortController();controller.abort();
 await assert.rejects(waitDecodeCapacity(decoder,controller.signal),/aborted/i);
});
