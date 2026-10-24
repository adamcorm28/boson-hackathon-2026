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

// Classic mode comes in light and dark.
export type Scheme = "light" | "dark";

const SCHEME_KEY = "dunder-mifflin-scheme";
const isScheme = (v: unknown): v is Scheme => v === "light" || v === "dark";

/** `?scheme=light|dark` wins, then the last choice on this browser, then the system setting. */
export function pickScheme(search: string, stored: string | null, systemPrefersDark: boolean): Scheme {
  const fromUrl = new URLSearchParams(search).get("scheme");
  if (isScheme(fromUrl)) return fromUrl;
  if (isScheme(stored)) return stored;
  return systemPrefersDark ? "dark" : "light";
}

export function loadStoredScheme(): string | null {
  try {
    return localStorage.getItem(SCHEME_KEY);
  } catch {
    return null;
  }
}

export function storeScheme(scheme: Scheme): void {
  try {
    localStorage.setItem(SCHEME_KEY, scheme);
  } catch {
    // ignore
  }
}
