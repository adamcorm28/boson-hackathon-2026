import { describe, expect, it } from "vitest";
import { otherMode, pickMode, pickScheme } from "./modes";

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

describe("pickScheme", () => {
  it("the URL wins, then the stored choice, then the system setting", () => {
    expect(pickScheme("?scheme=dark", "light", false)).toBe("dark");
    expect(pickScheme("", "light", true)).toBe("light");
    expect(pickScheme("", null, true)).toBe("dark");
    expect(pickScheme("", null, false)).toBe("light");
  });

  it("ignores junk values", () => {
    expect(pickScheme("?scheme=sepia", "neon", true)).toBe("dark");
  });
});
