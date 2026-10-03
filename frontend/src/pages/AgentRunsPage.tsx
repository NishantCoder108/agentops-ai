import { useEffect, useState } from "react";

import { listAgentRuns } from "../api/agentRuns";
import { errorMessage } from "../api/client";
import type { AgentRun } from "../api/types";
import { formatDuration, formatTimestamp, statusLabel } from "../agent-runs/format";
import RunTimeline from "../components/agent-runs/RunTimeline";
import ErrorBanner from "../components/ErrorBanner";
import PageHeader from "../components/PageHeader";

export default function AgentRunsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAgentRuns()
      .then((rows) => {
        if (!cancelled) {
          setRuns(rows);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(errorMessage(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <PageHeader
        title="Agent runs"
        description="How each run in the organization was produced, from the tools it called to the final answer."
      />
      <div className="page-body">
        {loading && <p className="muted">Loading runs…</p>}
        {error && <ErrorBanner message={error} />}
        {!loading && !error && runs.length === 0 && <p className="panel">No runs are listed here yet.</p>}
        {!loading && !error && runs.length > 0 && (
          <div className="run-list">
            {runs.map((run) => (
              <article className="run-card" key={run.id}>
                <dl className="run-meta">
                  <div>
                    <dt>Agent Run ID</dt>
                    <dd>
                      <code className="run-id">{run.id}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span className={`status status-${run.status}`}>{statusLabel(run.status)}</span>
                    </dd>
                  </div>
                  <div>
                    <dt>Start time</dt>
                    <dd>{formatTimestamp(run.started_at)}</dd>
                  </div>
                  <div>
                    <dt>Duration</dt>
                    <dd>{formatDuration(run.started_at, run.completed_at)}</dd>
                  </div>
                  <div className="run-answer">
                    <dt>Final answer</dt>
                    <dd className="run-text">{run.final_answer ?? "No final answer was recorded."}</dd>
                  </div>
                </dl>
                <RunTimeline run={run} />
              </article>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
