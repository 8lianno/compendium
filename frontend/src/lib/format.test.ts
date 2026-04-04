import { describe, expect, it } from "vitest";

import {
  formatContextWindow,
  formatPricing,
  highlightText,
  toProjectRelativePath,
} from "./format";

describe("format helpers", () => {
  it("highlights query terms without leaking raw HTML", () => {
    const highlighted = highlightText("<Climate> summary & forecast", "climate forecast");

    expect(highlighted).toContain("&lt;<mark>Climate</mark>&gt;");
    expect(highlighted).toContain("<mark>forecast</mark>");
    expect(highlighted).not.toContain("<Climate>");
  });

  it("normalizes project-relative wiki/raw/output paths", () => {
    expect(toProjectRelativePath("./wiki/notes/test.md")).toBe("wiki/notes/test.md");
    expect(toProjectRelativePath("/Users/ali/personal/compendium/wiki/notes/test.md")).toBe(
      "wiki/notes/test.md",
    );
    expect(toProjectRelativePath("/tmp/random.txt")).toBeNull();
  });

  it("formats context windows and pricing consistently", () => {
    expect(formatContextWindow(200000)).toBe("200,000");
    expect(formatContextWindow(null)).toBe("Unknown");
    expect(
      formatPricing({ input_per_million: 3.5, output_per_million: 15 }),
    ).toBe("$3.50 in / $15.00 out per 1M tokens");
    expect(formatPricing(null)).toBe("Pricing unavailable");
  });
});
