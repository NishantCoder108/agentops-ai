import type { ChatResponse, ConversationDetail, ConversationSummary } from "./types";
import { apiRequest } from "./client";

export function sendMessage(message: string, conversationId: string | null): Promise<ChatResponse> {
  return apiRequest<ChatResponse>("/api/v1/chat", {
    method: "POST",
    body: {
      message,
      ...(conversationId ? { conversation_id: conversationId } : {}),
    },
  });
}

export function listConversations(): Promise<ConversationSummary[]> {
  return apiRequest<ConversationSummary[]>("/api/v1/conversations");
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/api/v1/conversations/${conversationId}`);
}
