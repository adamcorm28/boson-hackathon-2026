import { afterEach, describe, expect, it, vi } from "vitest";
import { createFramer, MicBlockedError, startMic } from "./mic";

// ---- fakes for the browser audio APIs ----

const contexts: FakeAudioContext[] = [];
const nodes: FakeWorkletNode[] = [];

class FakeAudioContext {
  sampleRate = 48000;
  state = "running";
  destination = {};
  closed = false;
  audioWorklet = { addModule: vi.fn(async () => {}) };
  source = { connect: vi.fn(), disconnect: vi.fn() };
  constructor() {
    contexts.push(this);
  }
  createMediaStreamSource() {
    return this.source;
  }
  resume() {
    return Promise.resolve();
  }
  close() {
    this.closed = true;
    return Promise.resolve();
  }
}

class FakeWorkletNode {
  port: { onmessage: ((e: { data: Float32Array }) => void) | null } = { onmessage: null };
  connect = vi.fn();
  disconnect = vi.fn();
  constructor(
    readonly ctx: FakeAudioContext,
    readonly name: string,
  ) {
    nodes.push(this);
  }
}

function stubBrowser(getUserMedia: () => Promise<unknown>) {
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("AudioWorkletNode", FakeWorkletNode);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn(getUserMedia) } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  contexts.length = 0;
  nodes.length = 0;
});

// ---- tests ----

describe("createFramer", () => {
  it("emits 40 ms frames of 24 kHz PCM16 (1920 bytes) from 48 kHz blocks", () => {
    const frames: ArrayBuffer[] = [];
    const framer = createFramer(48000, (f) => frames.push(f));
    for (let i = 0; i < 30; i++) framer.push(new Float32Array(128)); // 3840 samples = 80 ms
    expect(frames.map((f) => f.byteLength)).toEqual([1920, 1920]);
  });

  it("handles 44.1 kHz mics and blocks that straddle frame boundaries", () => {
    const frames: ArrayBuffer[] = [];
    const framer = createFramer(44100, (f) => frames.push(f));
    framer.push(new Float32Array(1000));
    expect(frames).toHaveLength(0);
    framer.push(new Float32Array(1000)); // 2000 >= 1764
    expect(frames.map((f) => f.byteLength)).toEqual([1920]);
  });
});

describe("startMic", () => {
  it("startMic maps NotAllowedError to MicBlockedError", async () => {
    stubBrowser(() => Promise.reject(new DOMException("Permission denied", "NotAllowedError")));
    const err = await startMic(() => {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(MicBlockedError);
    expect((err as Error).message).toBe("Mic blocked — allow microphone and retry");
    expect(contexts[0].closed).toBe(true);
  });

  it("maps NotFoundError (no input device) to MicBlockedError", async () => {
    stubBrowser(() => Promise.reject(new DOMException("No device", "NotFoundError")));
    await expect(startMic(() => {})).rejects.toBeInstanceOf(MicBlockedError);
  });

  it("passes other errors through", async () => {
    stubBrowser(() => Promise.reject(new DOMException("Device busy", "NotReadableError")));
    const err = await startMic(() => {}).catch((e: unknown) => e);
    expect(err).not.toBeInstanceOf(MicBlockedError);
    expect((err as DOMException).name).toBe("NotReadableError");
  });

  it("streams worklet blocks as frames, and stop() releases the mic", async () => {
    const track = { stop: vi.fn() };
    stubBrowser(() => Promise.resolve({ getTracks: () => [track] }));
    const frames: ArrayBuffer[] = [];
    const mic = await startMic((f) => frames.push(f));

    const ctx = contexts[0];
    expect(ctx.audioWorklet.addModule).toHaveBeenCalledWith("/worklets/mic-processor.js");
    expect(nodes[0].name).toBe("mic-processor");
    expect(ctx.source.connect).toHaveBeenCalledWith(nodes[0]);

    nodes[0].port.onmessage?.({ data: new Float32Array(1920) }); // 40 ms at 48 kHz
    expect(frames.map((f) => f.byteLength)).toEqual([1920]);

    mic.stop();
    expect(track.stop).toHaveBeenCalled();
    expect(ctx.closed).toBe(true);
    expect(nodes[0].port.onmessage).toBeNull();
  });
});
