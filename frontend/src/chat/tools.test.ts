import { describe, expect, it } from "vitest";

import { toolLabels } from "./tools";

describe("toolLabels", () => {
  it("uses the display names once, in first-seen order", () => {
    expect(toolLabels(["calculator", "analytics", "calculator", "search_knowledge"])).toEqual([
      "Calculator",
      "Analytics Tool",
      "Knowledge Search",
    ]);
  });
});
