// PCM helpers. The gateway speaks PCM16 little-endian, 24 kHz, mono, both ways.
// (Int16Array uses the platform's byte order, which is little-endian on every browser platform.)

/** Resamples with linear interpolation. Works for any rate pair; we use it to go from the mic's rate to 24 kHz. */
export function downsample(input: Float32Array, inRate: number, outRate: number): Float32Array<ArrayBuffer> {
  if (inRate === outRate) return Float32Array.from(input);
  const ratio = inRate / outRate;
  const out = new Float32Array(Math.floor((input.length * outRate) / inRate));
  const last = input.length - 1;
  for (let i = 0; i < out.length; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, last);
    out[i] = input[i0] + (input[i1] - input[i0]) * (pos - i0);
  }
  return out;
}

/** Float samples in [-1, 1] (clamped) to PCM16. */
export function floatTo16(input: Float32Array): ArrayBuffer {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
  }
  return out.buffer;
}

/** PCM16 to float samples in [-1, 1]. A trailing odd byte is ignored. */
export function int16ToFloat(buf: ArrayBuffer): Float32Array<ArrayBuffer> {
  const samples = new Int16Array(buf, 0, buf.byteLength >> 1);
  const out = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    out[i] = s < 0 ? s / 0x8000 : s / 0x7fff;
  }
  return out;
}
