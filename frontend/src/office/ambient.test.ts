import { describe, expect, it } from "vitest";
import { createWorld, tickWorld, type Env, type Rng, type World } from "./ambient";
import { layoutDesks, type Desk } from "./map";

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

function run(n: number, env: Env, seed: number, each: (w: World) => void) {
  const rng = seeded(seed);
  let w = createWorld();
  for (let i = 0; i < n; i++) {
    w = tickWorld(w, env, rng);
    each(w);
  }
}

describe("ambient office", () => {
  it("idle employees say something now and then, one bubble each at a time", () => {
    const speakers = new Set<string>();
    run(1000, { desks, busy: null }, 5, (w) => {
      w.bubbles.forEach((b) => speakers.add(b.key));
      expect(new Set(w.bubbles.map((b) => b.key)).size).toBe(w.bubbles.length);
    });
    expect(speakers.size).toBeGreaterThanOrEqual(3);
  });

  it("leaves whoever you're on a call with alone", () => {
    run(2000, { desks, busy: "sales_lead" }, 11, (w) => {
      expect(w.bubbles.some((b) => b.key === "role:sales_lead")).toBe(false);
    });
  });

  it("bubbles go away after a few seconds", () => {
    let maxAge = 0;
    run(1000, { desks, busy: null }, 2, (w) => w.bubbles.forEach((b) => (maxAge = Math.max(maxAge, b.until - w.tick))));
    expect(maxAge).toBeGreaterThan(0);
    expect(maxAge).toBeLessThanOrEqual(14); // ~4 s at 300 ms per tick
  });
});
