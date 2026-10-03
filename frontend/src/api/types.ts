export type UserRole = "admin" | "user";

export type User = {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  organization_id: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type Source = {
  document_id: string;
  document_name: string;
  relevant_excerpt: string;
};

export type ChatResponse = {
  answer: string;
  sources: Source[];
  tools_used: string[];
  conversation_id?: string;
  run_id?: string;
};

export type ConversationSummary = {
  id: string;
  created_at: string;
};

export type ConversationMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type ConversationDetail = ConversationSummary & {
  messages: ConversationMessage[];
};

export type AgentRunTool = {
  tool_name: string;
  status: string;
  arguments: unknown;
  result_summary: string | null;
  started_at: string;
  completed_at: string | null;
};

export type AgentRun = {
  id: string;
  conversation_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  final_answer: string | null;
  tool_calls: AgentRunTool[];
};
