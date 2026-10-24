import { describe, expect, it } from "vitest";
import type { Desk } from "./map";
import { distance, nearby, step } from "./movement";

// A tiny test map: wall, floor, door and whiteboard.
const MAP = [
  "#####WW#",
  "#......#",
  "#......D",
  "########",
];
const desks: Desk[] = [
  { roleId: "jim", x: 3, y: 2 },
  { roleId: "dwight", x: 4, y: 2 },
];

describe("movement", () => {
  it("walls and desks block", () => {
    expect(step({ x: 1, y: 1 }, "up", desks, MAP)).toEqual({ x: 1, y: 1 }); // wall
    expect(step({ x: 1, y: 1 }, "left", desks, MAP)).toEqual({ x: 1, y: 1 }); // wall
    expect(step({ x: 2, y: 2 }, "right", desks, MAP)).toEqual({ x: 2, y: 2 }); // Jim's desk
    expect(step({ x: 5, y: 1 }, "up", desks, MAP)).toEqual({ x: 5, y: 1 }); // whiteboard
    expect(step({ x: 1, y: 1 }, "right", desks, MAP)).toEqual({ x: 2, y: 1 }); // floor
  });

  it("doors are walkable and the map edge blocks", () => {
    const atDoor = step({ x: 6, y: 2 }, "right", desks, MAP);
    expect(atDoor).toEqual({ x: 7, y: 2 });
    expect(step(atDoor, "right", desks, MAP)).toEqual(atDoor);
  });

  it("nearby desk detected", () => {
    expect(nearby({ x: 2, y: 2 }, desks, MAP)).toEqual({ kind: "desk", roleId: "jim" });
    expect(nearby({ x: 2, y: 1 }, desks, MAP)).toEqual({ kind: "desk", roleId: "jim" }); // diagonal counts
    expect(nearby({ x: 5, y: 2 }, desks, MAP)).toEqual({ kind: "desk", roleId: "dwight" });
  });

  it("picks the closer desk when two are in reach", () => {
    expect(nearby({ x: 3, y: 1 }, desks, MAP)).toEqual({ kind: "desk", roleId: "jim" }); // straight above Jim
    expect(nearby({ x: 4, y: 1 }, desks, MAP)).toEqual({ kind: "desk", roleId: "dwight" });
  });

  it("nearby whiteboard detected", () => {
    expect(nearby({ x: 6, y: 1 }, [], MAP)).toEqual({ kind: "board" });
    expect(nearby({ x: 1, y: 2 }, [], MAP)).toBeNull();
  });

  it("distance chebyshev", () => {
    expect(distance({ x: 0, y: 0 }, { x: 3, y: 1 })).toBe(3);
    expect(distance({ x: 2, y: 2 }, { x: 3, y: 3 })).toBe(1);
    expect(distance({ x: 5, y: 5 }, { x: 5, y: 5 })).toBe(0);
  });
});
