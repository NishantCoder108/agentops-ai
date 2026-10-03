import { describe, expect, it } from "vitest";

import { formatArguments, formatDuration, formatTimestamp, statusLabel } from "./format";

describe("agent run formatting", () => {
  it("formats duration from the stored timestamps", () => {
    expect(formatDuration("2026-10-03T10:00:00.000Z", null)).toBe("In progress");
    expect(formatDuration("2026-10-03T10:00:00.000Z", "2026-10-03T10:00:00.420Z")).toBe("420 ms");
    expect(formatDuration("2026-10-03T10:00:00.000Z", "2026-10-03T10:00:02.700Z")).toBe("2.7 s");
    expect(formatDuration("2026-10-03T10:00:00.000Z", "2026-10-03T10:01:05.000Z")).toBe("1m 5s");
  });

  it("leaves missing timestamps and arguments blank", () => {
    expect(formatTimestamp(null)).toBe("—");
    expect(formatTimestamp("not-a-date")).toBe("—");
    expect(formatArguments(null)).toBe("—");
    expect(formatArguments({ expression: "6 * 7" })).toBe('{\n  "expression": "6 * 7"\n}');
  });

  it("labels known run statuses", () => {
    expect(statusLabel("completed")).toBe("Completed");
    expect(statusLabel("running")).toBe("Running");
    expect(statusLabel("failed")).toBe("Failed");
  });
});
