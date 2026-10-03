const TOOL_LABELS: Record<string, string> = {
  analytics: "Analytics Tool",
  search_knowledge: "Knowledge Search",
  calculator: "Calculator",
};

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool;
}

export function toolLabels(tools: string[]): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();
  for (const tool of tools) {
    if (seen.has(tool)) {
      continue;
    }
    seen.add(tool);
    labels.push(toolLabel(tool));
  }
  return labels;
}
