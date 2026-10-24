import { describe, expect, it } from "vitest";
import { COFFEE_SPOT, createWorld, findPath, tickWorld, type Env, type Rng, type World } from "./ambient";
import { layoutDesks, type Desk } from "./map";
import { isWalkable } from "./movement";

/** Small seeded PRNG (mulberry32) so runs are repeatable. */
function seeded(seed: number): Rng {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const desks: Desk[] = layoutDesks(
  [
    ["ceo", "michael_office"],
    ["cfo", "accounting"],
    ["eng_lead", "annex"],
    ["engineer", "dwight_desk"],
    ["sales_lead", "jim_desk"],
  ].map(([id, desk]) => ({ id, name: id, title: "", reports_to: null, voice: "default", desk })),
);
const names = { ceo: "Michael", cfo: "Kevin", eng_lead: "Ryan", engineer: "Dwight", sales_lead: "Jim" };

function run(n: number, env: Env, seed = 1, each?: (w: World) => void): World {
  const rng = seeded(seed);
  let w = createWorld();
  for (let i = 0; i < n; i++) {
    w = tickWorld(w, env, rng);
    each?.(w);
  }
  return w;
}

describe("findPath", () => {
  const MAP = ["#####", "#.#.#", "#...#", "#####"];
  it("goes around walls", () => {
    expect(findPath({ x: 1, y: 1 }, [{ x: 3, y: 1 }], [], MAP)).toEqual([
      { x: 1, y: 2 },
      { x: 2, y: 2 },
      { x: 3, y: 2 },
      { x: 3, y: 1 },
    ]);
  });
  it("returns [] when already there and null when walled off", () => {
    expect(findPath({ x: 1, y: 1 }, [{ x: 1, y: 1 }], [], MAP)).toEqual([]);
    expect(findPath({ x: 1, y: 1 }, [{ x: 3, y: 1 }], [{ roleId: "x", x: 1, y: 2 }], MAP)).toBeNull();
  });
});

describe("ambient office", () => {
  it("interns bring coffee to desks, chat about it, and go back for more", () => {
    const env: Env = { desks, names, busy: null };
    const shouts: string[] = [];
    let deliveredTo = new Set<string>();
    let backAtMachine = false;
    run(800, env, 7, (w) => {
      for (const b of w.bubbles) if (b.key.startsWith("npc:") && !shouts.includes(b.text)) shouts.push(b.text);
      deliveredTo = new Set([...deliveredTo, ...Object.keys(w.coffee)]);
      if (w.tick > 100 && w.interns.some((i) => i.mode === "brewing" && i.pos.x === COFFEE_SPOT.x && i.pos.y === COFFEE_SPOT.y)) {
        backAtMachine = true;
      }
    });
    expect(deliveredTo.size).toBeGreaterThan(1);
    expect(shouts.some((s) => /^☕ .*(Michael|Kevin|Ryan|Dwight|Jim)/.test(s))).toBe(true);
    expect(backAtMachine).toBe(true);
  });

  it("interns never stand in walls, decor or desks", () => {
    run(1500, { desks, names, busy: null }, 3, (w) => {
      for (const i of w.interns) expect(isWalkable(i.pos, desks), `${i.id} at ${i.pos.x},${i.pos.y}`).toBe(true);
    });
  });

  it("leaves whoever you're on a call with alone", () => {
    run(2000, { desks, names, busy: "sales_lead" }, 11, (w) => {
      expect(w.bubbles.some((b) => b.key === "role:sales_lead")).toBe(false);
      expect(w.bubbles.some((b) => b.key.startsWith("npc:") && b.text.includes("Jim"))).toBe(false);
      expect(w.interns.some((i) => i.mode === "delivering" && i.to === "sales_lead" && i.path.length > 5)).toBe(false);
    });
  });

  it("idle employees say something now and then", () => {
    const quips = new Set<string>();
    run(1000, { desks, names, busy: null }, 5, (w) => w.bubbles.forEach((b) => b.key.startsWith("role:") && quips.add(b.key)));
    expect(quips.size).toBeGreaterThanOrEqual(3);
  });
});
