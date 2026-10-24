import { describe, expect, it } from "vitest";
import { initials, textColorFor } from "./avatarText";

describe("initials", () => {
  it("takes the first and last name's first letters", () => {
    expect(initials("Dwight Schrute")).toBe("DS");
    expect(initials("Dwight Kurt Schrute")).toBe("DS");
    expect(initials("  jim   halpert ")).toBe("JH");
  });

  it("handles one name or none", () => {
    expect(initials("Creed")).toBe("C");
    expect(initials("")).toBe("?");
  });
});

describe("textColorFor", () => {
  it("uses white on dark colors and dark text on light ones", () => {
    expect(textColorFor("#1c1c22")).toBe("#ffffff");
    expect(textColorFor("#2d3a5c")).toBe("#ffffff");
    expect(textColorFor("#dce6f2")).toBe("#1d2129");
    expect(textColorFor("#f2cba4")).toBe("#1d2129");
  });

  it("falls back to white for anything that isn't #rrggbb", () => {
    expect(textColorFor("red")).toBe("#ffffff");
  });
});
