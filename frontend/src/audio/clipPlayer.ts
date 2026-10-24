// Plays the gateway's lip-synced avatar clips back to back. Each clip is an MP4 that carries the
// reply's audio too, so for a role with an avatar this replaces the PCM player.

export interface ClipPlayer {
  /** The element to mount in the call window. */
  readonly video: HTMLVideoElement;
  enqueue(url: string): void;
  /** Stops the current clip and drops the queue (barge-in, hang-up). */
  stop(): void;
  /** True while a clip is playing or queued. */
  readonly playing: boolean;
}

export function createClipPlayer(): ClipPlayer {
  const video = document.createElement("video");
  video.className = "avatar-video";
  video.playsInline = true;
  video.preload = "auto";
  const queue: string[] = [];
  let active = false;

  // Shown only while a clip is actually playing; otherwise the idle loop underneath shows, so the
  // face never freezes or blanks while a clip loads or between clips.
  const next = () => {
    const url = queue.shift();
    active = url !== undefined;
    video.classList.remove("on");
    if (!url) return;
    video.src = url;
    video.play().catch(next); // a clip that won't play is skipped, not stuck
  };
  video.onplaying = () => {
    if (active) video.classList.add("on");
  };
  video.onended = next;
  video.onerror = () => {
    if (active) next();
  };

  return {
    video,
    enqueue(url) {
      queue.push(url);
      if (!active) next();
    },
    stop() {
      queue.length = 0;
      active = false;
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.classList.remove("on");
    },
    get playing() {
      return active;
    },
  };
}
