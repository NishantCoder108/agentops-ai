import type { AgentRun } from "./types";
import { apiRequest } from "./client";

export function listAgentRuns(): Promise<AgentRun[]> {
  return apiRequest<AgentRun[]>("/api/v1/agent-runs");
}
