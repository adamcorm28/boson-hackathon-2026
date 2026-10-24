import { describe, expect, it } from "vitest";
import { diffLineKind } from "./diff";

describe("diffLineKind", () => {
  it("colors adds, removes, hunks and headers", () => {
    expect(diffLineKind("+  return round2(discounted);")).toBe("add");
    expect(diffLineKind("-  return round2(subtotal);")).toBe("del");
    expect(diffLineKind("@@ -8,10 +8,10 @@")).toBe("hunk");
    expect(diffLineKind("+++ b/checkout/pricing.js")).toBe("meta");
    expect(diffLineKind("--- a/checkout/pricing.js")).toBe("meta");
    expect(diffLineKind("diff --git a/x b/x")).toBe("meta");
    expect(diffLineKind(" const BULK_DISCOUNT = 0.1;")).toBe("context");
    expect(diffLineKind("")).toBe("context");
  });
});
