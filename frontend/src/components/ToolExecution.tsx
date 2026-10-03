import { toolLabels } from "../chat/tools";

export default function ToolExecution({ tools }: { tools: string[] }) {
  const labels = toolLabels(tools);
  if (labels.length === 0) {
    return null;
  }
  return (
    <section className="tool-execution" aria-label="Agent execution">
      <h3>Agent execution</h3>
      <ul>
        {labels.map((label) => (
          <li key={label}>
            <span className="tool-check" aria-hidden="true">
              ✓
            </span>
            {label}
          </li>
        ))}
      </ul>
    </section>
  );
}
