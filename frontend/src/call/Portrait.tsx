// Original pixel-art caricatures (no likenesses): a 12x14 face drawn as SVG pixels.
import { useEffect, useState } from "react";

type Look = {
  hair: string;
  skin: string;
  shirt: string;
  tie: string;
  glasses?: boolean;
  bald?: boolean;
};

const LOOKS: Record<string, Look> = {
  ceo: { hair: "#3b2a1e", skin: "#f0c8a0", shirt: "#2d3a5c", tie: "#a8323e" }, // suit, red tie
  cfo: { hair: "#4a3a2c", skin: "#e8b48c", shirt: "#7a8fa8", tie: "#3c4f7a", bald: true },
  eng_lead: { hair: "#15110e", skin: "#d9a57a", shirt: "#1c1c22", tie: "#1c1c22" }, // black shirt, no tie
  engineer: { hair: "#5a3e22", skin: "#f2cfa8", shirt: "#c9a33b", tie: "#5a3e22", glasses: true }, // mustard shirt
  sales_lead: { hair: "#6b4a2e", skin: "#f2cba4", shirt: "#dce6f2", tie: "#48607c" },
};
const DEFAULT_LOOK: Look = { hair: "#555", skin: "#e6be98", shirt: "#6a6a80", tie: "#444" };

// h hair, s skin, e eye, m mouth, g glasses, b shirt, t tie, . empty
const FACE = [
  "...hhhhhh...",
  "..hhhhhhhh..",
  ".hhhhhhhhhh.",
  ".hssssssssh.",
  ".ssssssssss.",
  ".seessssees.",
  ".ssssssssss.",
  ".ssssssssss.",
  ".sssmmmmsss.",
  "..ssssssss..",
  "...ssssss...",
  "..bbbttbbb..",
  ".bbbbttbbbb.",
  "bbbbbttbbbbb",
];
const MOUTH_OPEN: Record<number, string> = { 8: ".sssmmmmsss.", 9: "..ssmmmmss.." };
const GLASSES: Record<number, string> = { 4: ".ggggssgggg.", 5: ".geegssgeeg.", 6: ".ggggssgggg." };
const BALD: Record<number, string> = { 0: "............", 1: "...ssssss...", 2: ".hssssssssh.", 3: ".hssssssssh." };

function rows(look: Look, open: boolean): string[] {
  return FACE.map((row, y) => {
    if (open && MOUTH_OPEN[y]) return MOUTH_OPEN[y];
    if (look.glasses && GLASSES[y]) return GLASSES[y];
    if (look.bald && BALD[y]) return BALD[y];
    return row;
  });
}

export function Portrait({ roleId, talking, pixel = 10 }: { roleId: string; talking: boolean; pixel?: number }) {
  const look = LOOKS[roleId] ?? DEFAULT_LOOK;
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!talking) {
      setOpen(false);
      return;
    }
    const t = setInterval(() => setOpen((o) => !o), 140);
    return () => clearInterval(t);
  }, [talking]);

  const colors: Record<string, string> = {
    h: look.hair,
    s: look.skin,
    e: "#1a1a1a",
    m: open ? "#5a1a1a" : "#8a4a3a",
    g: "#2a2a2a",
    b: look.shirt,
    t: look.tie,
  };

  const grid = rows(look, open);
  return (
    <svg
      className="portrait"
      width={12 * pixel}
      height={14 * pixel}
      viewBox="0 0 12 14"
      shapeRendering="crispEdges"
      role="img"
      aria-label={talking ? "talking" : "listening"}
    >
      {grid.flatMap((row, y) =>
        [...row].map((c, x) => (c === "." ? null : <rect key={`${x},${y}`} x={x} y={y} width={1} height={1} fill={colors[c]} />)),
      )}
    </svg>
  );
}
