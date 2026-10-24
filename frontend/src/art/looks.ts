// Colors for the original pixel-art caricatures (no likenesses), shared by portraits and office sprites.
export interface Look {
  hair: string;
  skin: string;
  shirt: string;
  tie: string;
  pants: string;
  /** Color for their cards on the whiteboard (defaults to the shirt). */
  accent?: string;
  glasses?: boolean;
  bald?: boolean;
}

export const LOOKS: Record<string, Look> = {
  ceo: { hair: "#3b2a1e", skin: "#f0c8a0", shirt: "#2d3a5c", tie: "#a8323e", pants: "#262f4a", accent: "#4a5d8f" }, // suit, red tie
  cfo: { hair: "#4a3a2c", skin: "#e8b48c", shirt: "#7a8fa8", tie: "#3c4f7a", pants: "#3a3a3a", bald: true },
  eng_lead: { hair: "#15110e", skin: "#d9a57a", shirt: "#1c1c22", tie: "#1c1c22", pants: "#2a2a30", accent: "#6b7080" }, // black shirt
  engineer: { hair: "#5a3e22", skin: "#f2cfa8", shirt: "#c9a33b", tie: "#5a3e22", pants: "#4a3a28", glasses: true }, // mustard
  sales_lead: { hair: "#6b4a2e", skin: "#f2cba4", shirt: "#dce6f2", tie: "#48607c", pants: "#2e3440", accent: "#48607c" },
};

export const DEFAULT_LOOK: Look = { hair: "#555", skin: "#e6be98", shirt: "#6a6a80", tie: "#444", pants: "#333" };

/** You: a visitor from corporate. */
export const PLAYER_LOOK: Look = { hair: "#a0a0a0", skin: "#efc9a4", shirt: "#3a3a42", tie: "#2a6a9a", pants: "#2a2a30" };

export const lookFor = (roleId: string): Look => LOOKS[roleId] ?? DEFAULT_LOOK;
export const accentFor = (roleId: string): string => lookFor(roleId).accent ?? lookFor(roleId).shirt;
