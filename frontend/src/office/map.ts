// The Scranton office floor, as ASCII tiles. Pure data + desk layout.
import type { Role } from "../api/types";

export interface Pos {
  x: number;
  y: number;
}

export interface Desk extends Pos {
  roleId: string;
}

// # wall · . floor · D door · W whiteboard (conference room wall) · R reception carpet
// Decor (blocking): C coffee machine · K copier · V water cooler · P plant
// Michael's office top-left, conference room top-right, bullpen in the middle with Jim and Dwight's
// facing desks, reception by the entrance (left), accounting corner bottom-left, the annex bottom-right,
// and the kitchenette (coffee, copier, water cooler) in the bottom-middle alcove.
export const OFFICE_MAP: string[] = [
  "####################WWW###",
  "#.....P#..........#......#",
  "#......#..........#......#",
  "#......#..........D......#",
  "#......D..........#......#",
  "########..........########",
  "#.......................P#",
  "#........................#",
  "D.RRR....................#",
  "#.RRR....................#",
  "#........................#",
  "#................#########",
  "#......#.........#.......#",
  "#......#.........D.......#",
  "#......#.K..C.V..#.......#",
  "##########################",
];

export const MAP_WIDTH = OFFICE_MAP[0].length;
export const MAP_HEIGHT = OFFICE_MAP.length;

/** Where the player starts: just inside the entrance. */
export const START: Pos = { x: 1, y: 8 };

export const DESK_SPOTS: Record<string, Pos> = {
  michael_office: { x: 3, y: 2 },
  jim_desk: { x: 12, y: 8 },
  dwight_desk: { x: 13, y: 8 }, // facing Jim's
  accounting: { x: 3, y: 13 },
  annex: { x: 21, y: 13 },
};

/** For roles with no (or an unknown) desk, in order. The first is the reception desk. */
export const AUTO_SPOTS: Pos[] = [
  { x: 3, y: 8 },
  { x: 17, y: 7 },
  { x: 20, y: 7 },
  { x: 8, y: 7 },
  { x: 17, y: 10 },
  { x: 20, y: 10 },
  { x: 8, y: 10 },
  { x: 5, y: 13 },
];

export function tileAt(map: string[], p: Pos): string {
  return map[p.y]?.[p.x] ?? "#";
}

/**
 * Known `desk` names get their fixed spot; everyone else takes the next free auto spot, in `roles` order.
 * A new role gets a desk with no code change. Roles beyond the last auto spot aren't placed.
 */
export function layoutDesks(roles: Role[]): Desk[] {
  const taken = new Set<string>();
  const key = (p: Pos) => `${p.x},${p.y}`;
  const desks: Desk[] = [];
  const unplaced: Role[] = [];

  for (const role of roles) {
    const spot = role.desk ? DESK_SPOTS[role.desk] : undefined;
    if (spot && !taken.has(key(spot))) {
      taken.add(key(spot));
      desks.push({ roleId: role.id, ...spot });
    } else {
      unplaced.push(role);
    }
  }

  const free = AUTO_SPOTS.filter((p) => !taken.has(key(p)));
  unplaced.forEach((role, i) => {
    if (free[i]) desks.push({ roleId: role.id, ...free[i] });
  });

  // Keep the input order so rendering is stable.
  const order = new Map(roles.map((r, i) => [r.id, i]));
  return desks.sort((a, b) => order.get(a.roleId)! - order.get(b.roleId)!);
}
