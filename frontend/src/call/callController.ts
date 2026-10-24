// Wires one call together: socket <-> player and mic, and every event into the reducer.
// Plain TypeScript so it can be tested without React; useCall is the thin hook around it.
import type { CallEvent, Gateway } from "../api/types";
import { MicBlockedError, startMic, type Mic } from "../audio/mic";
import { createClipPlayer, type ClipPlayer } from "../audio/clipPlayer";
import { joinLiveAvatar, type LiveAvatarView } from "../audio/liveAvatar";
import { createPlayer, type Player } from "../audio/player";
import type { CallAction } from "./callReducer";

export interface CallAudio {
  createContext(): AudioContext;
  createPlayer(ctx: AudioContext): Player;
  startMic(onFrame: (pcm: ArrayBuffer) => void): Promise<Mic>;
  /** Lip-synced avatar clips; without it, `avatar.clip` events are ignored. */
  createClipPlayer?(): ClipPlayer;
  /** Boson live avatar room; without it, `avatar.room` events are ignored. */
  joinLiveAvatar?(url: string, token: string, avatarIdentity: string): LiveAvatarView;
  /** Container the avatar videos go in, for the call window to mount. */
  createMedia?(): HTMLElement;
}

export const browserAudio: CallAudio = {
  createContext: () => new AudioContext(),
  createPlayer,
  startMic,
  createClipPlayer,
  joinLiveAvatar,
  createMedia: () => {
    const el = document.createElement("div");
    el.className = "avatar-media";
    return el;
  },
};

export interface CallController {
  hangup(): void;
  /** Extra audio into the call (the dev panel's fake "talk" buttons). */
  sendAudio(pcm: ArrayBuffer): void;
  retryMic(): void;
  /** Muted: mic frames are dropped instead of sent (the mic stays open). */
  setMuted(muted: boolean): void;
  /** True while the agent's audio is still coming out of the speakers. */
  readonly playing: boolean;
  /** The avatar videos (clips or the live avatar), for the call window to mount. */
  readonly media: HTMLElement | null;
}

/** Call from a click/keypress handler: the audio context and mic need the user gesture. */
export function startCall(
  gateway: Gateway,
  roleId: string,
  dispatch: (a: CallAction) => void,
  opts: { audio?: CallAudio; onEvent?: (e: CallEvent) => void } = {},
): CallController {
  const audio = opts.audio ?? browserAudio;
  dispatch({ type: "dial", roleId });

  const ctx = audio.createContext();
  const player = audio.createPlayer(ctx);
  const clips = audio.createClipPlayer?.() ?? null;
  const media = audio.createMedia?.() ?? null;
  if (clips) media?.appendChild(clips.video);
  let live: LiveAvatarView | null = null;
  const socket = gateway.openCall(roleId);
  let mic: Mic | null = null;
  let micStarting = false;
  let closed = false;
  let muted = false;

  socket.onEvent((e) => {
    if (closed) return;
    if (e.type === "barge_in") {
      player.stop(); // before anything else: cut the audio now
      clips?.stop();
    }
    if (e.type === "avatar.clip") clips?.enqueue(e.url);
    if (e.type === "avatar.room" && !live && audio.joinLiveAvatar) {
      live = audio.joinLiveAvatar(e.url, e.token, e.avatar_identity);
      media?.appendChild(live.video);
    }
    opts.onEvent?.(e);
    dispatch(e);
  });
  socket.onAudio((pcm) => {
    if (!closed) player.enqueue(pcm);
  });
  socket.onClose((code) => {
    if (closed) return;
    closed = true;
    mic?.stop();
    mic = null;
    player.stop();
    clips?.stop();
    live?.close();
    void ctx.close();
    dispatch({ type: "closed", code });
  });

  const openMic = () => {
    if (mic || micStarting || closed) return;
    micStarting = true;
    audio.startMic((frame) => {
      if (!muted) socket.sendAudio(frame);
    }).then(
      (m) => {
        micStarting = false;
        if (closed) return m.stop();
        mic = m;
        dispatch({ type: "mic_ok" });
      },
      (err: unknown) => {
        micStarting = false;
        if (closed) return;
        const message = err instanceof MicBlockedError ? undefined : `Mic unavailable: ${err instanceof Error ? err.message : String(err)}`;
        dispatch(message ? { type: "mic_blocked", message } : { type: "mic_blocked" });
      },
    );
  };
  openMic();

  return {
    hangup: () => socket.hangup(),
    sendAudio: (pcm) => socket.sendAudio(pcm),
    retryMic: openMic,
    setMuted: (m) => {
      muted = m;
    },
    get playing() {
      return !closed && (player.playing || (clips?.playing ?? false));
    },
    media,
  };
}
