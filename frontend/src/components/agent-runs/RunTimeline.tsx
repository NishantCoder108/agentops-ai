import { formatArguments, formatTimestamp, statusLabel } from "../../agent-runs/format";
import { toolLabel, toolLabels } from "../../chat/tools";
import type { AgentRun } from "../../api/types";

export default function RunTimeline({ run }: { run: AgentRun }) {
  const selected = toolLabels(run.tool_calls.map((call) => call.tool_name));
  const planning = selected.length === 0 ? "No tools were selected." : `Selected ${selected.join(", ")}.`;

  return (
    <ol className="timeline">
      <li className="timeline-step">
        <div className="timeline-heading">
          <h3>Planning</h3>
          <time dateTime={run.started_at}>{formatTimestamp(run.started_at)}</time>
        </div>
        <p>{planning}</p>
      </li>
      <li className="timeline-step">
        <h3>Tool calls</h3>
        {run.tool_calls.length === 0 ? (
          <p>No tools were called.</p>
        ) : (
          <div className="tool-list">
            {run.tool_calls.map((call, index) => (
              <article className="tool-block" key={`${call.tool_name}-${call.started_at}-${index}`}>
                <div className="timeline-heading">
                  <h4>{toolLabel(call.tool_name)}</h4>
                  <time dateTime={call.started_at}>{formatTimestamp(call.started_at)}</time>
                </div>
                <p className="tool-status">{statusLabel(call.status)}</p>
                <h5>Tool arguments</h5>
                <pre className="tool-json">{formatArguments(call.arguments)}</pre>
                <h5>Tool result summary</h5>
                <p>{call.result_summary ?? (call.status === "running" ? "In progress" : "No result was recorded.")}</p>
              </article>
            ))}
          </div>
        )}
      </li>
      <li className="timeline-step">
        <div className="timeline-heading">
          <h3>Final response</h3>
          <time dateTime={run.completed_at ?? undefined}>{formatTimestamp(run.completed_at)}</time>
        </div>
        <p className="run-text">{run.final_answer ?? "No final answer was recorded."}</p>
      </li>
    </ol>
  );
}
