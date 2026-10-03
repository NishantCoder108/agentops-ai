import { describe, expect, it } from "vitest";

import { activityLabel } from "./activity";

describe("activityLabel", () => {
  it("names each stage the chat page shows while a reply is streaming", () => {
    expect(activityLabel("thinking")).toBe("Thinking...");
    expect(activityLabel("tool", "analytics")).toBe("Calling Analytics Tool...");
    expect(activityLabel("tool", "search_knowledge")).toBe("Searching Knowledge...");
    expect(activityLabel("tool", "calculator")).toBe("Calling Calculator...");
    expect(activityLabel("generating")).toBe("Generating response...");
  });
});
