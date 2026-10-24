// Ambient office life, purely cosmetic: interns on coffee runs and idle one-liners.
// Pure: tickWorld(world, env, rng) -> next world. One tick = TICK_MS.
import { OFFICE_MAP, type Desk, type Pos } from "./map";
import { isWalkable } from "./movement";

export type Rng = () => number;

export const TICK_MS = 300;
const ticks = (seconds: number) => Math.round((seconds * 1000) / TICK_MS);

export interface Intern {
  id: string;
  name: string;
  pos: Pos;
  mode: "brewing" | "delivering" | "handing" | "returning";
  path: Pos[];
  /** roleId the coffee is for. */
  to: string | null;
  waitUntil: number;
}

export interface Bubble {
  /** "role:<id>" or "npc:<intern id>". */
  key: string;
  text: string;
  until: number;
}

export interface World {
  tick: number;
  interns: Intern[];
  bubbles: Bubble[];
  /** roleId -> tick until which a coffee cup sits on their desk. */
  coffee: Record<string, number>;
}

export interface Env {
  desks: Desk[];
  /** First names by roleId, for "Coffee for Dwight!". */
  names: Record<string, string>;
  /** The role you're on a call with: left alone. */
  busy: string | null;
  map?: string[];
}

export function findTile(ch: string, map: string[] = OFFICE_MAP): Pos {
  for (let y = 0; y < map.length; y++) {
    const x = map[y].indexOf(ch);
    if (x >= 0) return { x, y };
  }
  throw new Error(`no '${ch}' on the map`);
}

export const COFFEE_MACHINE = findTile("C");
/** Where interns stand to brew: in front of the machine. */
export const COFFEE_SPOT: Pos = { x: COFFEE_MACHINE.x, y: COFFEE_MACHINE.y - 1 };

const NEIGHBOURS: Pos[] = [
  { x: 0, y: -1 },
  { x: 0, y: 1 },
  { x: -1, y: 0 },
  { x: 1, y: 0 },
];
const add = (a: Pos, b: Pos): Pos => ({ x: a.x + b.x, y: a.y + b.y });
const same = (a: Pos, b: Pos) => a.x === b.x && a.y === b.y;
const pick = <T,>(items: T[], rng: Rng): T => items[Math.floor(rng() * items.length) % items.length];

/** Shortest 4-way path to any goal (excluding the start), [] if already there, null if unreachable. */
export function findPath(from: Pos, goals: Pos[], desks: Desk[], map: string[] = OFFICE_MAP): Pos[] | null {
  if (goals.some((g) => same(g, from))) return [];
  const key = (p: Pos) => `${p.x},${p.y}`;
  const goalKeys = new Set(goals.map(key));
  const prev = new Map<string, Pos | null>([[key(from), null]]);
  const queue: Pos[] = [from];
  while (queue.length) {
    const p = queue.shift()!;
    for (const d of NEIGHBOURS) {
      const n = add(p, d);
      const k = key(n);
      if (prev.has(k) || !isWalkable(n, desks, map)) continue;
      prev.set(k, p);
      if (goalKeys.has(k)) {
        const path: Pos[] = [n];
        for (let c = p; !same(c, from); c = prev.get(key(c))!) path.unshift(c);
        return path;
      }
      queue.push(n);
    }
  }
  return null;
}

// ---- lines (text personas only; at most one bit each) ----

const QUIPS: Record<string, string[]> = {
  ceo: ["Who wants to hear a joke?", "I declare… a meeting!", "World's Best Boss, reporting for duty.", "Conference room, five minutes!"],
  cfo: ["Is it lunch yet?", "The vending machine owes me 75 cents.", "I have a number for everything.", "Mmm. Chili."],
  eng_lead: ["We should pivot to the cloud.", "This is basically a startup.", "Have you heard of Web 3.0?", "Disrupt paper."],
  engineer: ["Beets. Best crop. Fact.", "Who put my stapler in jello?!", "I am ready for any emergency.", "Assistant TO the… never mind."],
  sales_lead: ["*looks at camera*", "Another day in paradise.", "Dwight, is that your stapler?", "Just closed a deal. Casually."],
};
const GENERIC_QUIPS = ["Busy busy!", "Is it Friday yet?", "Who took my yogurt?"];

const THANKS: Record<string, string[]> = {
  ceo: ["Is this from Starbucks? It better be.", "My intern! Best intern."],
  cfo: ["Is there a muffin with this?", "Extra sugar? …Extra sugar."],
  eng_lead: ["Oat milk? I only do oat milk.", "Put it on my startup's tab."],
  engineer: ["Did you poison this? …Fine.", "Black. Like my soul. Thank you."],
  sales_lead: ["Thanks! Don't tell Dwight.", "You're a lifesaver."],
};
const GENERIC_THANKS = ["Thanks!", "Oh, nice!"];

const INTERN_SHOUTS = ["☕ Coffee for {name}!", "☕ One coffee, {name}!", "☕ {name}, your coffee!"];

// ---- world ----

export function createWorld(): World {
  return {
    tick: 0,
    interns: [
      { id: "intern-1", name: "Kyle", pos: COFFEE_SPOT, mode: "brewing", path: [], to: null, waitUntil: ticks(3) },
      { id: "intern-2", name: "Priya", pos: { x: COFFEE_SPOT.x - 1, y: COFFEE_SPOT.y }, mode: "brewing", path: [], to: null, waitUntil: ticks(9) },
    ],
    bubbles: [],
    coffee: {},
  };
}

function say(bubbles: Bubble[], key: string, text: string, until: number): Bubble[] {
  return [...bubbles.filter((b) => b.key !== key), { key, text, until }];
}

export function tickWorld(world: World, env: Env, rng: Rng): World {
  const map = env.map ?? OFFICE_MAP;
  const tick = world.tick + 1;
  let bubbles = world.bubbles.filter((b) => b.until > tick);
  const coffee = Object.fromEntries(Object.entries(world.coffee).filter(([, until]) => until > tick));
  const name = (roleId: string) => env.names[roleId] ?? roleId;

  const interns = world.interns.map((intern): Intern => {
    switch (intern.mode) {
      case "brewing": {
        if (tick < intern.waitUntil) return intern;
        const targets = env.desks.filter((d) => d.roleId !== env.busy);
        if (!targets.length) return { ...intern, waitUntil: tick + ticks(3) };
        const desk = pick(targets, rng);
        const goals = NEIGHBOURS.map((d) => add(desk, d)).filter((p) => isWalkable(p, env.desks, map));
        const path = findPath(intern.pos, goals, env.desks, map);
        if (!path) return { ...intern, waitUntil: tick + ticks(3) };
        return { ...intern, mode: "delivering", path, to: desk.roleId };
      }
      case "delivering": {
        if (intern.path.length) return { ...intern, pos: intern.path[0], path: intern.path.slice(1) };
        const to = intern.to!;
        coffee[to] = tick + ticks(45);
        if (to !== env.busy) {
          bubbles = say(bubbles, `npc:${intern.id}`, pick(INTERN_SHOUTS, rng).replace("{name}", name(to)), tick + ticks(2.5));
        }
        return { ...intern, mode: "handing", waitUntil: tick + ticks(2.5) };
      }
      case "handing": {
        if (tick < intern.waitUntil) return intern;
        if (intern.to && intern.to !== env.busy) {
          bubbles = say(bubbles, `role:${intern.to}`, pick(THANKS[intern.to] ?? GENERIC_THANKS, rng), tick + ticks(3));
        }
        const path = findPath(intern.pos, [COFFEE_SPOT], env.desks, map) ?? [];
        return { ...intern, mode: "returning", path, to: null };
      }
      case "returning": {
        if (intern.path.length) return { ...intern, pos: intern.path[0], path: intern.path.slice(1) };
        return { ...intern, mode: "brewing", waitUntil: tick + ticks(4 + rng() * 8) };
      }
    }
  });

  // An idle employee says something now and then.
  if (rng() < 1 / 30) {
    const talking = new Set(bubbles.map((b) => b.key));
    const idle = env.desks.filter((d) => d.roleId !== env.busy && !talking.has(`role:${d.roleId}`));
    if (idle.length) {
      const d = pick(idle, rng);
      bubbles = say(bubbles, `role:${d.roleId}`, pick(QUIPS[d.roleId] ?? GENERIC_QUIPS, rng), tick + ticks(4));
    }
  }

  return { tick, interns, bubbles, coffee };
}
