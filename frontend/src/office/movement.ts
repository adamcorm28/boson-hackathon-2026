// Walking and "what am I next to?". Pure functions over the tile map.
import { OFFICE_MAP, tileAt, type Desk, type Pos } from "./map";

export type Dir = "up" | "down" | "left" | "right";

const DELTA: Record<Dir, Pos> = {
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
};

const BLOCKING = new Set(["#", "W", "C", "K", "V", "P"]);

export function isWalkable(p: Pos, desks: Desk[], map: string[] = OFFICE_MAP): boolean {
  if (p.y < 0 || p.y >= map.length || p.x < 0 || p.x >= map[p.y].length) return false;
  if (BLOCKING.has(tileAt(map, p))) return false;
  return !desks.some((d) => d.x === p.x && d.y === p.y);
}

/** One tile in `dir`, or the same position if that tile is blocked. */
export function step(pos: Pos, dir: Dir, desks: Desk[], map: string[] = OFFICE_MAP): Pos {
  const next = { x: pos.x + DELTA[dir].x, y: pos.y + DELTA[dir].y };
  return isWalkable(next, desks, map) ? next : pos;
}

/** Chebyshev distance: diagonal neighbours are 1 apart. */
export function distance(a: Pos, b: Pos): number {
  return Math.max(Math.abs(a.x - b.x), Math.abs(a.y - b.y));
}

export type Nearby = { kind: "desk"; roleId: string } | { kind: "board" } | null;

/** The desk (closest first) or whiteboard within 1 tile, including diagonals. */
export function nearby(pos: Pos, desks: Desk[], map: string[] = OFFICE_MAP): Nearby {
  const manhattan = (d: Pos) => Math.abs(d.x - pos.x) + Math.abs(d.y - pos.y);
  const close = desks.filter((d) => distance(pos, d) <= 1).sort((a, b) => manhattan(a) - manhattan(b));
  if (close.length) return { kind: "desk", roleId: close[0].roleId };

  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      if (tileAt(map, { x: pos.x + dx, y: pos.y + dy }) === "W") return { kind: "board" };
    }
  }
  return null;
}
