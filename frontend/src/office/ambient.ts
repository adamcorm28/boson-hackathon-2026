// Ambient office life, purely cosmetic: idle employees say a one-liner now and then.
// Pure: tickWorld(world, env, rng) -> next world. One tick = TICK_MS.
import type { Desk } from "./map";

export type Rng = () => number;

export const TICK_MS = 300;
const ticks = (seconds: number) => Math.round((seconds * 1000) / TICK_MS);

export interface Bubble {
  /** "role:<id>". */
  key: string;
  text: string;
  until: number;
}

export interface World {
  tick: number;
  bubbles: Bubble[];
}

export interface Env {
  desks: Desk[];
  /** The role you're on a call with: left alone. */
  busy: string | null;
}

const pick = <T,>(items: T[], rng: Rng): T => items[Math.floor(rng() * items.length) % items.length];

// Text personas only; one bit each.
const QUIPS: Record<string, string[]> = {
  ceo: ["Who wants to hear a joke?", "I declare… a meeting!", "World's Best Boss, reporting for duty.", "Conference room, five minutes!"],
  cfo: ["Is it lunch yet?", "The vending machine owes me 75 cents.", "I have a number for everything.", "Mmm. Chili."],
  eng_lead: ["We should pivot to the cloud.", "This is basically a startup.", "Have you heard of Web 3.0?", "Disrupt paper."],
  engineer: ["Beets. Best crop. Fact.", "Who put my stapler in jello?!", "I am ready for any emergency.", "Assistant TO the… never mind."],
  sales_lead: ["*looks at camera*", "Another day in paradise.", "Dwight, is that your stapler?", "Just closed a deal. Casually."],
};
const GENERIC_QUIPS = ["Busy busy!", "Is it Friday yet?", "Who took my yogurt?"];

export function createWorld(): World {
  return { tick: 0, bubbles: [] };
}

export function tickWorld(world: World, env: Env, rng: Rng): World {
  const tick = world.tick + 1;
  let bubbles = world.bubbles.filter((b) => b.until > tick);

  if (rng() < 1 / 30) {
    const talking = new Set(bubbles.map((b) => b.key));
    const idle = env.desks.filter((d) => d.roleId !== env.busy && !talking.has(`role:${d.roleId}`));
    if (idle.length) {
      const d = pick(idle, rng);
      bubbles = [...bubbles, { key: `role:${d.roleId}`, text: pick(QUIPS[d.roleId] ?? GENERIC_QUIPS, rng), until: tick + ticks(4) }];
    }
  }

  return { tick, bubbles };
}
