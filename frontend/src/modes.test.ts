import { describe, expect, it } from "vitest";
import { otherMode, pickMode } from "./modes";

describe("pickMode", () => {
  it("the URL wins", () => {
    expect(pickMode("?mode=classic", "arcade")).toBe("classic");
    expect(pickMode("?notitle&mode=arcade", "classic")).toBe("arcade");
  });

  it("then the last choice on this browser, then arcade", () => {
    expect(pickMode("", "classic")).toBe("classic");
    expect(pickMode("", null)).toBe("arcade");
  });

  it("ignores junk values", () => {
    expect(pickMode("?mode=vr", "nonsense")).toBe("arcade");
    expect(pickMode("?mode=", "classic")).toBe("classic");
  });

  it("otherMode flips between the two", () => {
    expect(otherMode("arcade")).toBe("classic");
    expect(otherMode("classic")).toBe("arcade");
  });
});
