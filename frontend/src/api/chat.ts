import type { ChatResponse, ConversationDetail, ConversationSummary } from "./types";
import { ApiError, apiRequest, responseError } from "./client";
import { readToken, UNAUTHORIZED_EVENT, writeToken } from "../auth/storage";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

export function sendMessage(message: string, conversationId: string | null): Promise<ChatResponse> {
  return apiRequest<ChatResponse>("/api/v1/chat", {
    method: "POST",
    body: {
      message,
      ...(conversationId ? { conversation_id: conversationId } : {}),
    },
  });
}

export type StreamHandlers = {
  onStatus: (status: "thinking" | "tool" | "generating", tool: string | null) => void;
  onToken: (text: string, replace: boolean) => void;
  onDone: (response: ChatResponse) => void;
};

export async function streamMessage(
  message: string,
  conversationId: string | null,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const headers = new Headers({
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  });
  const token = readToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
      signal,
    });
  } catch (err) {
    if (signal.aborted) {
      throw err;
    }
    throw new ApiError(0, "network_error", "Could not reach the server.");
  }

  if (response.status === 401 && token) {
    writeToken(null);
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  if (!response.body) {
    throw new ApiError(0, "network_error", "Could not reach the server.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const parsed = parseEvent(block);
      if (!parsed) {
        continue;
      }
      if (parsed.event === "status") {
        const status = parsed.data.status;
        if (status === "thinking" || status === "tool" || status === "generating") {
          handlers.onStatus(status, typeof parsed.data.tool === "string" ? parsed.data.tool : null);
        }
      } else if (parsed.event === "token") {
        handlers.onToken(String(parsed.data.text ?? ""), Boolean(parsed.data.replace));
      } else if (parsed.event === "done") {
        finished = true;
        handlers.onDone(parsed.data as ChatResponse);
      } else if (parsed.event === "error") {
        throw new ApiError(
          0,
          String(parsed.data.code ?? "agent_failed"),
          String(parsed.data.message ?? "The agent could not complete this request."),
        );
      }
    }
  }
  if (!finished && !signal.aborted) {
    throw new ApiError(0, "agent_failed", "The agent did not finish the response.");
  }
}

function parseEvent(block: string): { event: string; data: Record<string, unknown> } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return { event, data: JSON.parse(dataLines.join("\n")) as Record<string, unknown> };
}

export function listConversations(): Promise<ConversationSummary[]> {
  return apiRequest<ConversationSummary[]>("/api/v1/conversations");
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/api/v1/conversations/${conversationId}`);
}
