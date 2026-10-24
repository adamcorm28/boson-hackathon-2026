// Gapless playback of PCM16 24 kHz chunks that may arrive faster than real time.
import { int16ToFloat } from "./pcm";

export const PLAYBACK_RATE = 24000;

export interface Player {
  enqueue(pcm: ArrayBuffer): void;
  /** Stops everything playing or queued immediately (barge-in), and resets the schedule. */
  stop(): void;
  /** True while scheduled audio is still playing. */
  readonly playing: boolean;
}

export function createPlayer(ctx: AudioContext): Player {
  const sources = new Set<AudioBufferSourceNode>();
  let endOfLast = 0;

  return {
    enqueue(pcm) {
      const samples = int16ToFloat(pcm);
      if (samples.length === 0) return;
      if (ctx.state === "suspended") void ctx.resume();

      const buffer = ctx.createBuffer(1, samples.length, PLAYBACK_RATE); // the browser resamples to the device rate
      buffer.copyToChannel(samples, 0);
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);

      // Back to back with the previous chunk; if the queue already drained, start now.
      const startAt = Math.max(ctx.currentTime, endOfLast);
      src.start(startAt);
      endOfLast = startAt + buffer.duration;

      sources.add(src);
      src.onended = () => {
        sources.delete(src);
        src.disconnect();
      };
    },

    stop() {
      for (const src of sources) {
        src.onended = null;
        try {
          src.stop();
        } catch {
          // already stopped
        }
        src.disconnect();
      }
      sources.clear();
      endOfLast = 0;
    },

    get playing() {
      return endOfLast > ctx.currentTime;
    },
  };
}
