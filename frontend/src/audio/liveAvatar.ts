// Watches the call's Boson live avatar in its LiveKit room: lip-synced video plus the agent's
// voice, published by the avatar in sync. The gateway sends the room and a subscribe-only token.
import { Room, RoomEvent, Track } from "livekit-client";

export interface LiveAvatarView {
  /** Shows the avatar once its video track arrives (gets the "on" class then). */
  readonly video: HTMLVideoElement;
  close(): void;
}

export function joinLiveAvatar(url: string, token: string, avatarIdentity: string): LiveAvatarView {
  const video = document.createElement("video");
  video.className = "avatar-video live";
  video.autoplay = true;
  video.playsInline = true;
  video.muted = true; // the voice plays from its own audio element
  const audios: HTMLMediaElement[] = [];
  const room = new Room();

  room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
    if (participant.identity !== avatarIdentity) return;
    if (track.kind === Track.Kind.Video) {
      track.attach(video);
      video.classList.add("on");
    } else if (track.kind === Track.Kind.Audio) {
      const el = track.attach();
      el.style.display = "none";
      document.body.appendChild(el);
      audios.push(el);
    }
  });

  room
    .connect(url, token)
    .then(() => room.startAudio()) // the dial keypress already unlocked audio playback
    .catch((err: unknown) => console.warn("live avatar: can't join the room", err));

  return {
    video,
    close() {
      void room.disconnect();
      for (const el of audios) el.remove();
      video.classList.remove("on");
      video.srcObject = null;
    },
  };
}
