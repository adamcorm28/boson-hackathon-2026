// Runs on the audio thread. Batches the 128-sample render quanta of input channel 0
// into 1024-sample Float32 blocks (~21 ms at 48 kHz) and posts them to the main thread.
// Writes nothing to its output, so it plays silence.
const BLOCK = 1024;

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(BLOCK);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      let offset = 0;
      while (offset < channel.length) {
        const n = Math.min(BLOCK - this.filled, channel.length - offset);
        this.buf.set(channel.subarray(offset, offset + n), this.filled);
        this.filled += n;
        offset += n;
        if (this.filled === BLOCK) {
          this.port.postMessage(this.buf, [this.buf.buffer]);
          this.buf = new Float32Array(BLOCK);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
