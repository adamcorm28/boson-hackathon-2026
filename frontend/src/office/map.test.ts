import { describe, expect, it } from "vitest";
import type { Role } from "../api/types";
import { AUTO_SPOTS, DESK_SPOTS, layoutDesks, OFFICE_MAP, START, type Pos } from "./map";
import { isWalkable, step, type Dir } from "./movement";

const role = (id: string, desk?: string | null): Role => ({ id, name: id, title: "", reports_to: null, voice: "default", desk });

const CAST = [
  role("ceo", "michael_office"),
  role("cfo", "accounting"),
  role("eng_lead", "annex"),
  role("engineer", "dwight_desk"),
  role("sales_lead", "jim_desk"),
];

describe("OFFICE_MAP", () => {
  it("is a rectangle with a wall all around (doors aside)", () => {
    const width = OFFICE_MAP[0].length;
    expect(OFFICE_MAP.every((row) => row.length === width)).toBe(true);
    const edge = [...OFFICE_MAP[0], ...OFFICE_MAP.at(-1)!, ...OFFICE_MAP.map((r) => r[0]), ...OFFICE_MAP.map((r) => r.at(-1)!)];
    expect(edge.every((c) => "#DW".includes(c))).toBe(true);
  });

  it("every desk spot is next to a tile you can reach from the entrance, and so is the whiteboard", () => {
    const desks = layoutDesks([...CAST, ...AUTO_SPOTS.map((_, i) => role(`extra${i}`))]);
    expect(desks).toHaveLength(5 + AUTO_SPOTS.length);

    // flood fill from the start, with every desk in place
    const seen = new Set<string>([`${START.x},${START.y}`]);
    const queue: Pos[] = [START];
    while (queue.length) {
      const p = queue.shift()!;
      for (const dir of ["up", "down", "left", "right"] as Dir[]) {
        const n = step(p, dir, desks);
        const k = `${n.x},${n.y}`;
        if (!seen.has(k)) {
          seen.add(k);
          queue.push(n);
        }
      }
    }
    const reachableNextTo = (t: Pos) =>
      [-1, 0, 1].some((dy) => [-1, 0, 1].some((dx) => seen.has(`${t.x + dx},${t.y + dy}`)));

    for (const d of desks) expect(reachableNextTo(d), `desk of ${d.roleId}`).toBe(true);
    const wb = OFFICE_MAP.flatMap((row, y) => [...row].flatMap((c, x) => (c === "W" ? [{ x, y }] : [])));
    expect(wb.length).toBeGreaterThan(0);
    expect(wb.some(reachableNextTo)).toBe(true);
  });

  it("spots sit on floor tiles and the start is walkable", () => {
    for (const p of [...Object.values(DESK_SPOTS), ...AUTO_SPOTS]) expect(".R").toContain(OFFICE_MAP[p.y][p.x]);
    expect(isWalkable(START, [])).toBe(true);
  });
});

describe("layoutDesks", () => {
  it("known desks placed at fixed spots", () => {
    const desks = layoutDesks(CAST);
    expect(desks).toEqual([
      { roleId: "ceo", ...DESK_SPOTS.michael_office },
      { roleId: "cfo", ...DESK_SPOTS.accounting },
      { roleId: "eng_lead", ...DESK_SPOTS.annex },
      { roleId: "engineer", ...DESK_SPOTS.dwight_desk },
      { roleId: "sales_lead", ...DESK_SPOTS.jim_desk },
    ]);
  });

  it("unknown role gets auto spot", () => {
    const desks = layoutDesks([...CAST, { ...role("reception"), desk: undefined }]);
    expect(desks.at(-1)).toEqual({ roleId: "reception", ...AUTO_SPOTS[0] });
  });

  it("unknown desk names, missing desks and duplicates take auto spots in order", () => {
    const desks = layoutDesks([role("a", "the_moon"), role("b", "jim_desk"), role("c", "jim_desk"), role("d", null)]);
    expect(desks).toEqual([
      { roleId: "a", ...AUTO_SPOTS[0] },
      { roleId: "b", ...DESK_SPOTS.jim_desk },
      { roleId: "c", ...AUTO_SPOTS[1] },
      { roleId: "d", ...AUTO_SPOTS[2] },
    ]);
  });

  it("more roles than spots: the extras are left out instead of throwing", () => {
    const many = Array.from({ length: AUTO_SPOTS.length + 3 }, (_, i) => role(`r${i}`));
    expect(layoutDesks(many)).toHaveLength(AUTO_SPOTS.length);
  });
});
