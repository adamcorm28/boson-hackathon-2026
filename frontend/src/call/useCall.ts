import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { CallEvent, Gateway } from "../api/types";
import { startCall, type CallController } from "./callController";
import { callReducer, initialCallState } from "./callReducer";

const DISMISS_MS = 1500; // how long "Call ended" stays up
const DISMISS_ERROR_MS = 3000;

export function useCall(gateway: Gateway, opts: { onEvent?: (e: CallEvent) => void } = {}) {
  const [state, dispatch] = useReducer(callReducer, initialCallState);
  const [playing, setPlaying] = useState(false);
  const [media, setMedia] = useState<HTMLElement | null>(null);
  const [muted, setMuted] = useState(false);
  const ctrl = useRef<CallController | null>(null);
  const onEvent = useRef(opts.onEvent);
  onEvent.current = opts.onEvent;

  /** Call from a click/keypress handler. Ignored while a call is open. */
  const dial = useCallback(
    (roleId: string) => {
      if (ctrl.current) return;
      const me: CallController = startCall(
        gateway,
        roleId,
        (a) => {
          if (a.type === "closed" && ctrl.current === me) {
            ctrl.current = null;
            setMedia(null);
          }
          dispatch(a);
        },
        { onEvent: (e) => onEvent.current?.(e) },
      );
      ctrl.current = me;
      setMedia(me.media);
      setMuted(false);
    },
    [gateway],
  );

  const hangup = useCallback(() => {
    if (ctrl.current) ctrl.current.hangup();
    else dispatch({ type: "dismiss" }); // Esc on the "Call ended" card closes it
  }, []);

  const retryMic = useCallback(() => ctrl.current?.retryMic(), []);
  const toggleMute = useCallback(() => {
    setMuted((m) => {
      ctrl.current?.setMuted(!m);
      return !m;
    });
  }, []);
  const sendAudio = useCallback((pcm: ArrayBuffer) => ctrl.current?.sendAudio(pcm), []);

  // Close the window by itself once the call is over (also when the server ended it).
  useEffect(() => {
    if (state.status !== "ended") return;
    const t = setTimeout(() => dispatch({ type: "dismiss" }), state.error ? DISMISS_ERROR_MS : DISMISS_MS);
    return () => clearTimeout(t);
  }, [state.status, state.error]);

  // agent.speaking turns false when the server finishes sending, which is before playback finishes.
  useEffect(() => {
    if (state.status !== "live") {
      setPlaying(false);
      return;
    }
    const t = setInterval(() => setPlaying(ctrl.current?.playing ?? false), 100);
    return () => clearInterval(t);
  }, [state.status]);

  useEffect(() => () => ctrl.current?.hangup(), []);

  return { state, dial, hangup, retryMic, sendAudio, media, muted, toggleMute, talking: state.speaking || playing };
}
