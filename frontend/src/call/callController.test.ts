import { describe, expect, it, vi } from "vitest";
import type { CallEvent, CallSocket, Gateway } from "../api/types";
import { MicBlockedError } from "../audio/mic";
import { startCall, type CallAudio } from "./callController";
import type { CallAction } from "./callReducer";

function fakeSocket() {
  const h = {
    audio: [] as ((pcm: ArrayBuffer) => void)[],
    event: [] as ((e: CallEvent) => void)[],
    close: [] as ((code: number) => void)[],
  };
  const socket: CallSocket & { sent: ArrayBuffer[]; hungUp: boolean } = {
    sent: [],
    hungUp: false,
    sendAudio(pcm) {
      this.sent.push(pcm);
    },
    hangup() {
      this.hungUp = true;
    },
    onAudio: (cb) => void h.audio.push(cb),
    onEvent: (cb) => void h.event.push(cb),
    onClose: (cb) => void h.close.push(cb),
  };
  return {
    socket,
    emit: (e: CallEvent) => h.event.forEach((cb) => cb(e)),
    audio: (pcm: ArrayBuffer) => h.audio.forEach((cb) => cb(pcm)),
    close: (code: number) => h.close.forEach((cb) => cb(code)),
  };
}

function setup(micResult: () => Promise<{ stop(): void }> = async () => ({ stop: vi.fn() })) {
  const sock = fakeSocket();
  const gateway = { openCall: vi.fn(() => sock.socket) } as unknown as Gateway;
  const ctx = { close: vi.fn(async () => {}) };
  const player = { enqueue: vi.fn(), stop: vi.fn(), playing: false };
  let micFrame: ((pcm: ArrayBuffer) => void) | null = null;
  const audio: CallAudio = {
    createContext: () => ctx as unknown as AudioContext,
    createPlayer: () => player,
    startMic: vi.fn((onFrame: (pcm: ArrayBuffer) => void) => {
      micFrame = onFrame;
      return micResult();
    }),
  };
  const actions: CallAction[] = [];
  const order: string[] = [];
  player.stop.mockImplementation(() => void order.push("player.stop"));
  const dispatch = (a: CallAction) => {
    actions.push(a);
    order.push(`dispatch:${a.type}`);
  };
  const call = startCall(gateway, "ceo", dispatch, { audio });
  return { call, sock, gateway, ctx, player, audio, actions, order, micFrame: () => micFrame };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("startCall", () => {
  it("dials, forwards events, plays audio and streams the mic", async () => {
    const t = setup();
    await flush();
    expect(t.gateway.openCall).toHaveBeenCalledWith("ceo");
    expect(t.actions[0]).toEqual({ type: "dial", roleId: "ceo" });

    t.sock.emit({ type: "call.started", role: "ceo" });
    const chunk = new ArrayBuffer(4800);
    t.sock.audio(chunk);
    const frame = new ArrayBuffer(1920);
    t.micFrame()?.(frame);

    expect(t.actions).toContainEqual({ type: "call.started", role: "ceo" });
    expect(t.actions).toContainEqual({ type: "mic_ok" });
    expect(t.player.enqueue).toHaveBeenCalledWith(chunk);
    expect(t.sock.socket.sent).toEqual([frame]);
  });

  it("barge_in stops local playback straight away", () => {
    const t = setup();
    t.sock.emit({ type: "barge_in" });
    expect(t.order.slice(-2)).toEqual(["player.stop", "dispatch:barge_in"]);
  });

  it("a server-side end cleans up and closes the window state", async () => {
    const mic = { stop: vi.fn() };
    const t = setup(async () => mic);
    await flush();
    t.sock.emit({ type: "call.ended", reason: "idle_timeout" });
    t.sock.close(1000);

    expect(mic.stop).toHaveBeenCalled();
    expect(t.player.stop).toHaveBeenCalled();
    expect(t.ctx.close).toHaveBeenCalled();
    expect(t.actions.slice(-2)).toEqual([
      { type: "call.ended", reason: "idle_timeout" },
      { type: "closed", code: 1000 },
    ]);
    // nothing leaks through after the close
    t.sock.audio(new ArrayBuffer(10));
    expect(t.player.enqueue).not.toHaveBeenCalled();
  });

  it("hangup asks the socket to hang up", () => {
    const t = setup();
    t.call.hangup();
    expect(t.sock.socket.hungUp).toBe(true);
  });

  it("a blocked mic dispatches mic_blocked, and retryMic tries again", async () => {
    let attempt = 0;
    const t = setup(async () => {
      attempt++;
      if (attempt === 1) throw new MicBlockedError("NotAllowedError");
      return { stop: vi.fn() };
    });
    await flush();
    expect(t.actions).toContainEqual({ type: "mic_blocked" });

    t.call.retryMic();
    await flush();
    expect(t.audio.startMic).toHaveBeenCalledTimes(2);
    expect(t.actions.at(-1)).toEqual({ type: "mic_ok" });
  });

  it("other mic failures say what went wrong", async () => {
    const t = setup(async () => {
      throw new DOMException("Device in use", "NotReadableError");
    });
    await flush();
    expect(t.actions.at(-1)).toMatchObject({ type: "mic_blocked", message: expect.stringContaining("Device in use") });
  });

  it("a mic that starts after the call already closed is stopped at once", async () => {
    const mic = { stop: vi.fn() };
    let resolveMic: (m: { stop(): void }) => void = () => {};
    const t = setup(() => new Promise((r) => (resolveMic = r)));
    t.sock.close(4409);
    resolveMic(mic);
    await flush();
    expect(mic.stop).toHaveBeenCalled();
    expect(t.actions.at(-1)).toEqual({ type: "closed", code: 4409 });
  });
});
