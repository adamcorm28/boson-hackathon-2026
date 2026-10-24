// Mic capture: AudioWorklet at the device rate -> 40 ms frames of PCM16 24 kHz mono.
import { downsample, floatTo16 } from "./pcm";

export const TARGET_RATE = 24000;
export const FRAME_MS = 40;
const WORKLET_URL = `${import.meta.env.BASE_URL}worklets/mic-processor.js`;

export class MicBlockedError extends Error {
  readonly reason: string;
  constructor(reason: string) {
    super("Mic blocked — allow microphone and retry");
    this.name = "MicBlockedError";
    this.reason = reason;
  }
}

export interface Mic {
  stop(): void;
}

/** Collects float blocks at `inRate` and emits 40 ms PCM16 frames at 24 kHz (1920 bytes each). */
export function createFramer(inRate: number, onFrame: (pcm: ArrayBuffer) => void) {
  const pending = new Float32Array(Math.round((inRate * FRAME_MS) / 1000));
  let filled = 0;
  return {
    push(block: Float32Array) {
      let offset = 0;
      while (offset < block.length) {
        const n = Math.min(pending.length - filled, block.length - offset);
        pending.set(block.subarray(offset, offset + n), filled);
        filled += n;
        offset += n;
        if (filled === pending.length) {
          onFrame(floatTo16(downsample(pending, inRate, TARGET_RATE)));
          filled = 0;
        }
      }
    },
  };
}

function hasName(err: unknown, ...names: string[]): boolean {
  return typeof err === "object" && err !== null && names.includes((err as { name?: unknown }).name as string);
}

/**
 * Starts the mic. Call it from a click/keypress handler so the AudioContext is allowed to run.
 * Throws MicBlockedError if permission is denied or there's no input device.
 */
export async function startMic(onFrame: (pcm: ArrayBuffer) => void): Promise<Mic> {
  // Created before the first await, while we still have the user gesture.
  // It runs at the device rate: Firefox can't connect a mic to a context at a different rate.
  const ctx = new AudioContext();

  let stream: MediaStream;
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new MicBlockedError("no mediaDevices (needs https or localhost)");
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    void ctx.close();
    if (err instanceof MicBlockedError) throw err;
    if (hasName(err, "NotAllowedError", "NotFoundError")) throw new MicBlockedError((err as Error).name);
    throw err;
  }

  try {
    await ctx.audioWorklet.addModule(WORKLET_URL);
  } catch (err) {
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close();
    throw err;
  }
  if (ctx.state === "suspended") void ctx.resume(); // not awaited: it can stay pending without a gesture

  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "mic-processor");
  const framer = createFramer(ctx.sampleRate, onFrame);
  node.port.onmessage = (e: MessageEvent<Float32Array>) => framer.push(e.data);
  source.connect(node);
  node.connect(ctx.destination); // the processor outputs silence; being connected keeps it running everywhere

  let stopped = false;
  return {
    stop() {
      if (stopped) return;
      stopped = true;
      node.port.onmessage = null;
      source.disconnect();
      node.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}
