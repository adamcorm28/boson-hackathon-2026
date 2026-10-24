import { describe, expect, it } from "vitest";
import { downsample, floatTo16, int16ToFloat } from "./pcm";

describe("downsample", () => {
  it("downsample 48k→24k halves length", () => {
    const input = Float32Array.from({ length: 960 }, (_, i) => Math.sin(i / 10));
    const out = downsample(input, 48000, 24000);
    expect(out.length).toBe(480);
    expect(out[10]).toBeCloseTo(input[20], 6); // 2:1 lands exactly on every other sample
  });

  it("turns a 40 ms block at 44.1 kHz into exactly 960 samples", () => {
    expect(downsample(new Float32Array(1764), 44100, 24000).length).toBe(960);
  });

  it("interpolates linearly between samples", () => {
    const out = downsample(Float32Array.from([0, 1, 2, 3, 4, 5]), 3, 2); // positions 0, 1.5, 3, 4.5
    expect(Array.from(out)).toEqual([0, 1.5, 3, 4.5]);
  });

  it("returns a copy when the rates match", () => {
    const input = Float32Array.from([0.1, 0.2]);
    const out = downsample(input, 24000, 24000);
    expect(out).not.toBe(input);
    expect(Array.from(out)).toEqual(Array.from(input));
  });
});

describe("PCM16 conversion", () => {
  it("floatTo16 clamps", () => {
    expect(Array.from(new Int16Array(floatTo16(Float32Array.from([1.5, -2]))))).toEqual([32767, -32768]);
  });

  it("writes little-endian 16-bit samples", () => {
    const view = new DataView(floatTo16(Float32Array.from([0.5, -0.5])));
    expect(view.byteLength).toBe(4);
    expect(view.getInt16(0, true)).toBe(16384);
    expect(view.getInt16(2, true)).toBe(-16384);
  });

  it("round trip within 1/32768", () => {
    const input = Float32Array.from({ length: 2000 }, (_, i) => (i === 0 ? -1 : i === 1 ? 1 : Math.random() * 2 - 1));
    const back = int16ToFloat(floatTo16(input));
    let worst = 0;
    for (let i = 0; i < input.length; i++) worst = Math.max(worst, Math.abs(back[i] - input[i]));
    expect(worst).toBeLessThanOrEqual(1 / 32768);
  });

  it("int16ToFloat ignores a trailing odd byte", () => {
    expect(int16ToFloat(new ArrayBuffer(5)).length).toBe(2);
  });
});
