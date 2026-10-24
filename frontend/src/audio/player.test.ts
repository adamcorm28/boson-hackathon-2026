import { describe, expect, it, vi } from "vitest";
import { createPlayer } from "./player";

class FakeSource {
  buffer: { duration: number } | null = null;
  startedAt: number | null = null;
  stopped = false;
  connected = false;
  onended: (() => void) | null = null;
  connect() {
    this.connected = true;
  }
  disconnect() {
    this.connected = false;
  }
  start(when = 0) {
    this.startedAt = when;
  }
  stop() {
    this.stopped = true;
  }
}

class FakeAudioContext {
  currentTime = 0;
  state: "running" | "suspended" = "running";
  destination = {};
  sources: FakeSource[] = [];
  copied: Float32Array[] = [];
  resume = vi.fn(async () => {
    this.state = "running";
  });
  createBuffer(_channels: number, length: number, sampleRate: number) {
    return { duration: length / sampleRate, copyToChannel: (data: Float32Array) => this.copied.push(data.slice()) };
  }
  createBufferSource() {
    const s = new FakeSource();
    this.sources.push(s);
    return s;
  }
}

const ms100 = () => new ArrayBuffer(2400 * 2); // 100 ms of PCM16 at 24 kHz

function setup() {
  const ctx = new FakeAudioContext();
  const player = createPlayer(ctx as unknown as AudioContext);
  return { ctx, player };
}

describe("player", () => {
  it("player schedules back-to-back", () => {
    const { ctx, player } = setup();
    player.enqueue(ms100());
    player.enqueue(ms100());
    expect(ctx.sources.map((s) => s.startedAt)).toEqual([0, expect.closeTo(0.1, 9)]);
    expect(ctx.sources.every((s) => s.connected)).toBe(true);
  });

  it("starts a late chunk now, not in the past", () => {
    const { ctx, player } = setup();
    player.enqueue(ms100());
    ctx.currentTime = 0.5; // the queue drained a while ago
    player.enqueue(ms100());
    expect(ctx.sources[1].startedAt).toBe(0.5);
  });

  it("reports playing while scheduled audio remains", () => {
    const { ctx, player } = setup();
    expect(player.playing).toBe(false);
    player.enqueue(ms100());
    player.enqueue(ms100());
    ctx.currentTime = 0.15;
    expect(player.playing).toBe(true);
    ctx.currentTime = 0.25;
    expect(player.playing).toBe(false);
  });

  it("stop clears queued sources", () => {
    const { ctx, player } = setup();
    player.enqueue(ms100());
    player.enqueue(ms100());
    player.enqueue(ms100());
    player.stop();

    expect(ctx.sources.every((s) => s.stopped && !s.connected)).toBe(true);
    expect(player.playing).toBe(false);

    ctx.currentTime = 0.05;
    player.enqueue(ms100()); // schedule was reset: plays now, not after the 0.3 s that was cancelled
    expect(ctx.sources[3].startedAt).toBe(0.05);
  });

  it("decodes PCM16 into the buffer", () => {
    const { ctx, player } = setup();
    player.enqueue(Int16Array.from([16384, -32768]).buffer);
    expect(Array.from(ctx.copied[0])).toEqual([expect.closeTo(0.5, 3), -1]);
  });

  it("ignores empty chunks and resumes a suspended context", () => {
    const { ctx, player } = setup();
    player.enqueue(new ArrayBuffer(0));
    expect(ctx.sources).toHaveLength(0);

    ctx.state = "suspended";
    player.enqueue(ms100());
    expect(ctx.resume).toHaveBeenCalled();
  });
});
