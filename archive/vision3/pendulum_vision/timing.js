/* Clock intervals, not a claim of synchronized sensor/display clocks. */
(function(root){
  function clockSample(start,end,serverSeconds){
    if(![start,end,serverSeconds].every(Number.isFinite)||end<start)return null;
    return {offset_ms:(start+end)/2-serverSeconds*1000,uncertainty_ms:(end-start)/2,at_ms:end};
  }
  function frameAge(originSeconds,timestampUs,now,sample){
    if(![originSeconds,timestampUs,now].every(Number.isFinite)||!sample||now-sample.at_ms>30000)return null;
    const age=now-(originSeconds*1000+timestampUs/1000+sample.offset_ms);
    return {estimate_ms:Math.max(0,age),uncertainty_ms:sample.uncertainty_ms,
            lower_ms:Math.max(0,age-sample.uncertainty_ms),upper_ms:Math.max(0,age+sample.uncertainty_ms)};
  }
  const api={clockSample,frameAge};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.VisionTiming=api;
})(globalThis);
