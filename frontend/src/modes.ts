// Two ways to use the office: walk around it (arcade) or pick from a phone contact list (classic).
export type Mode = "arcade" | "classic";

const STORAGE_KEY = "dunder-mifflin-mode";
const isMode = (v: unknown): v is Mode => v === "arcade" || v === "classic";

/** `?mode=classic|arcade` wins, then the last choice on this browser, then arcade. */
export function pickMode(search: string, stored: string | null): Mode {
  const fromUrl = new URLSearchParams(search).get("mode");
  if (isMode(fromUrl)) return fromUrl;
  if (isMode(stored)) return stored;
  return "arcade";
}

export const otherMode = (mode: Mode): Mode => (mode === "arcade" ? "classic" : "arcade");

// Remembering the choice is a convenience: storage can be blocked (private windows), so never throw.
export function loadStoredMode(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeMode(mode: Mode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // ignore
  }
}
