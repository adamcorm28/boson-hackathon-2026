// Original full-body pixel sprite (10x14) for the office floor.
import type { Look } from "./looks";

// h hair, s skin, e eye, m mouth, g glasses, b shirt, t tie, p pants, k shoes, . empty
const BODY = [
  "..hhhhhh..",
  ".hhhhhhhh.",
  ".hssssssh.",
  ".sesssses.",
  ".ssssssss.",
  "..ssmmss..",
  "...ssss...",
  ".bbbttbbb.",
  "bbbbttbbbb",
  "sbbbttbbbs",
  ".bbbbbbbb.",
  ".pppppppp.",
  ".ppp..ppp.",
  ".kkk..kkk.",
];
const GLASSES: Record<number, string> = { 3: ".gegssgeg." };
const BALD: Record<number, string> = { 0: "..........", 1: "..ssssss..", 2: ".hssssssh." };
// One-frame walk: shift the legs.
const STEP: Record<number, string> = { 12: ".ppp...pp.", 13: ".kkk...kk." };

export function Sprite({ look, pixel = 3, stepping = false }: { look: Look; pixel?: number; stepping?: boolean }) {
  const colors: Record<string, string> = {
    h: look.hair,
    s: look.skin,
    e: "#1a1a1a",
    m: "#8a4a3a",
    g: "#2a2a2a",
    b: look.shirt,
    t: look.tie,
    p: look.pants,
    k: "#1a1414",
  };
  const rows = BODY.map((row, y) => (stepping && STEP[y]) || (look.glasses && GLASSES[y]) || (look.bald && BALD[y]) || row);

  return (
    <svg className="sprite" width={10 * pixel} height={14 * pixel} viewBox="0 0 10 14" shapeRendering="crispEdges" aria-hidden>
      {rows.flatMap((row, y) =>
        [...row].map((c, x) => (c === "." ? null : <rect key={`${x},${y}`} x={x} y={y} width={1} height={1} fill={colors[c]} />)),
      )}
    </svg>
  );
}
