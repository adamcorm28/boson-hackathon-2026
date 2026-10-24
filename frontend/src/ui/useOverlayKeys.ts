import { useEffect, useRef } from "react";

// Open overlays, oldest first. Only the top one reacts to keys.
const stack: object[] = [];

/**
 * While an overlay is open, Esc (and any extra keys) close it, and the key doesn't reach the
 * office or the call window underneath (so Esc closes the overlay without hanging up).
 * With overlays on top of each other, only the topmost one closes.
 */
export function useOverlayKeys(open: boolean, onClose: () => void, extraKeys: string[] = []) {
  const close = useRef(onClose);
  close.current = onClose;
  const keys = extraKeys.join(",");

  useEffect(() => {
    if (!open) return;
    const me = {};
    stack.push(me);
    const closeKeys = new Set(["escape", ...keys.split(",").filter(Boolean)]);
    const onKey = (e: KeyboardEvent) => {
      if (stack.at(-1) !== me || !closeKeys.has(e.key.toLowerCase())) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      close.current();
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => {
      window.removeEventListener("keydown", onKey, { capture: true });
      stack.splice(stack.indexOf(me), 1);
    };
  }, [open, keys]);
}
