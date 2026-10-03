import { toolLabel } from "./tools";

export function activityLabel(
  status: "thinking" | "tool" | "generating",
  tool?: string | null,
): string {
  if (status === "thinking") {
    return "Thinking...";
  }
  if (status === "generating") {
    return "Generating response...";
  }
  if (tool === "analytics") {
    return "Calling Analytics Tool...";
  }
  if (tool === "search_knowledge") {
    return "Searching Knowledge...";
  }
  return `Calling ${toolLabel(tool ?? "tool")}...`;
}
