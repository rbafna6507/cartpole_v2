/* Read-only length-prefixed Annex-B video. No camera settings or rig commands. */
(() => {
  const MAX_PACKET_BYTES = 8 * 1024 * 1024;
  async function waitCapacity(decoder, signal) {
    if (signal.aborted || decoder.state === 'closed') throw Error('Video stopped');
    const start = performance.now();
    while (decoder.decodeQueueSize >= 6) {
      if (signal.aborted || decoder.state === 'closed') throw Error('Video stopped');
      if (performance.now() - start > 250) throw Error('Video decoder stalled');
      await new Promise(resolve => setTimeout(resolve, 4));
    }
  }
  class PortalVideo {
    constructor(canvas, callbacks = {}) {
      this.canvas = canvas; this.context = canvas.getContext('2d', {alpha: false}); this.callbacks = callbacks;
      this.generation = 0; this.controller = null; this.decoder = null; this.latest = null; this.frames = 0;
    }
    stop() {
      this.generation++; this.controller?.abort(); clearTimeout(this.reconnectTimer); clearInterval(this.watchdog);
      cancelAnimationFrame(this.paintRequest);
      if (this.decoder && this.decoder.state !== 'closed') this.decoder.close();
      if (this.latest) { this.latest.close(); this.latest = null; }
      this.context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
    start(token) {
      this.stop(); this.token = token; this.frames = 0;
      if (!('VideoDecoder' in window) || !('EncodedVideoChunk' in window)) {
        this.callbacks.fallback?.('This browser does not support H.264 WebCodecs. Showing sampled JPEG preview.'); return;
      }
      this.connect(this.generation);
    }
    paint(generation) {
      if (generation !== this.generation) return;
      if (this.latest) {
        const frame = this.latest; this.latest = null;
        this.canvas.width = frame.displayWidth; this.canvas.height = frame.displayHeight;
        this.context.drawImage(frame, 0, 0); frame.close();
        this.callbacks.frame?.();
      }
      this.paintRequest = requestAnimationFrame(() => this.paint(generation));
    }
    async connect(generation) {
      if (generation !== this.generation) return;
      const controller = new AbortController(); this.controller = controller;
      let decoder, reader, watchdog, failure = null, received = 0;
      let lastFrame = performance.now();
      this.callbacks.status?.('Connecting video');
      try {
        decoder = new VideoDecoder({
          output: frame => {
            if (generation !== this.generation || controller.signal.aborted) { frame.close(); return; }
            if (this.latest) this.latest.close();
            this.latest = frame; this.frames++; received++; lastFrame = performance.now();
          },
          error: error => { failure = error; controller.abort(); },
        });
        this.decoder = decoder; decoder.configure({codec: 'avc1.42E028', optimizeForLatency: true});
        watchdog = setInterval(() => {
          if (performance.now() - lastFrame > 7000) { failure = Error('No video frames received'); controller.abort(); }
        }, 1000);
        this.watchdog = watchdog;
        const response = await fetch('/api/video', {headers: {Authorization: 'Bearer ' + this.token}, cache: 'no-store', signal: controller.signal});
        if (generation !== this.generation || controller.signal.aborted) { await response.body?.cancel().catch(() => {}); return; }
        if (!response.ok || !response.body) throw Error('Video stream unavailable (' + response.status + ')');
        reader = response.body.getReader(); let pending = new Uint8Array(0), waitKey = true;
        let startTimestamp = null, arrivalStart = 0, newestTimestamp = 0;
        cancelAnimationFrame(this.paintRequest); this.paint(generation);
        while (!controller.signal.aborted && generation === this.generation) {
          const {value, done} = await reader.read(); if (done) break;
          if (pending.length + value.length > MAX_PACKET_BYTES * 2 + 26) throw Error('Video buffer limit exceeded');
          const joined = new Uint8Array(pending.length + value.length); joined.set(pending); joined.set(value, pending.length); pending = joined;
          let offset = 0;
          while (pending.length - offset >= 13) {
            const header = new DataView(pending.buffer, pending.byteOffset + offset, 13), size = header.getUint32(0);
            if (size < 1 || size > MAX_PACKET_BYTES) throw Error('Invalid video packet size');
            if (pending.length - offset < 13 + size) break;
            const timestamp = Number(header.getBigUint64(4)), key = header.getUint8(12) !== 0;
            if (!Number.isSafeInteger(timestamp)) throw Error('Invalid video timestamp');
            if (startTimestamp === null) { startTimestamp = timestamp; arrivalStart = performance.now(); }
            newestTimestamp = timestamp;
            await waitCapacity(decoder, controller.signal);
            if (!waitKey || key) {
              waitKey = false;
              decoder.decode(new EncodedVideoChunk({type: key ? 'key' : 'delta', timestamp, data: pending.slice(offset + 13, offset + 13 + size)}));
            }
            offset += 13 + size;
          }
          pending = pending.slice(offset);
          if (startTimestamp !== null && performance.now() - arrivalStart - (newestTimestamp - startTimestamp) / 1000 > 1500) throw Error('Reconnecting to current video');
        }
      } catch (error) { if (!failure) failure = error; }
      finally {
        clearInterval(watchdog);
        if (generation === this.generation) cancelAnimationFrame(this.paintRequest);
        if (reader) await reader.cancel().catch(() => {});
        if (decoder && decoder.state !== 'closed') decoder.close();
        if (generation === this.generation && this.latest) { this.latest.close(); this.latest = null; }
        if (generation === this.generation) {
          if (received === 0 && this.frames === 0) {
            this.callbacks.fallback?.((failure?.message || 'No video frames received') + '. Showing sampled JPEG preview.');
          } else {
            this.callbacks.status?.('Reconnecting video');
            this.reconnectTimer = setTimeout(() => this.connect(generation), 750);
          }
        }
      }
    }
  }
  window.PortalVideo = PortalVideo;
})();
