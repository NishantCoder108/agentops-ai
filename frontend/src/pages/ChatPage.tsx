import { useEffect, useRef, useState, type FormEvent } from "react";

import { errorMessage } from "../api/client";
import { getConversation, listConversations, streamMessage } from "../api/chat";
import type { ChatResponse, ConversationSummary } from "../api/types";
import { activityLabel } from "../chat/activity";
import ChatComposer from "../components/chat/ChatComposer";
import ConversationList from "../components/chat/ConversationList";
import MessageList, { type ThreadMessage } from "../components/chat/MessageList";
import ErrorBanner from "../components/ErrorBanner";

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [loadingReply, setLoadingReply] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    let cancelled = false;
    listConversations()
      .then((rows) => {
        if (!cancelled) {
          setConversations(rows);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setHistoryError(errorMessage(err));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingHistory(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, loadingReply, activity]);

  function cancelReply() {
    abortRef.current?.abort();
    abortRef.current = null;
  }

  function startNewChat() {
    cancelReply();
    requestSeq.current += 1;
    setConversationId(null);
    setMessages([]);
    setError(null);
    setActivity(null);
    setLoadingReply(false);
    setLoadingThread(false);
  }

  async function openConversation(id: string) {
    cancelReply();
    const seq = ++requestSeq.current;
    setConversationId(id);
    setError(null);
    setActivity(null);
    setLoadingReply(false);
    setLoadingThread(true);
    setMessages([]);
    try {
      const detail = await getConversation(id);
      if (requestSeq.current !== seq) {
        return;
      }
      setMessages(
        detail.messages.map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
        })),
      );
    } catch (err) {
      if (requestSeq.current === seq) {
        setError(errorMessage(err));
      }
    } finally {
      if (requestSeq.current === seq) {
        setLoadingThread(false);
      }
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || loadingReply) {
      return;
    }
    cancelReply();
    const controller = new AbortController();
    abortRef.current = controller;
    const seq = ++requestSeq.current;
    const assistantId = crypto.randomUUID();
    setDraft("");
    setError(null);
    setActivity("Thinking...");
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: text }]);
    setLoadingReply(true);
    try {
      await streamMessage(
        text,
        conversationId,
        {
          onStatus: (status, tool) => {
            if (requestSeq.current === seq) {
              setActivity(activityLabel(status, tool));
            }
          },
          onToken: (token, replace) => {
            if (requestSeq.current === seq) {
              setMessages((current) => applyToken(current, assistantId, token, replace));
            }
          },
          onDone: (response) => {
            if (requestSeq.current !== seq) {
              return;
            }
            rememberConversation(response, setConversationId, setConversations);
            setMessages((current) => applyDone(current, assistantId, response));
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted || requestSeq.current !== seq) {
        return;
      }
      setMessages((current) => current.filter((message) => message.id !== assistantId));
      setError(errorMessage(err));
    } finally {
      if (requestSeq.current === seq) {
        setLoadingReply(false);
        setActivity(null);
      }
    }
  }

  const busy = loadingReply || loadingThread;

  return (
    <div className="chat-page">
      <aside className="history" aria-label="Message history">
        <div className="history-toolbar">
          <h1>Chat</h1>
          <button type="button" className="text-button" onClick={startNewChat}>
            New chat
          </button>
        </div>
        {loadingHistory && <p className="muted">Loading history…</p>}
        {historyError && <ErrorBanner message={historyError} />}
        {!loadingHistory && (
          <ConversationList conversations={conversations} selectedId={conversationId} onSelect={openConversation} />
        )}
      </aside>
      <section className="thread" aria-label="Conversation">
        <div className="thread-scroll">
          {messages.length === 0 && !busy && (
            <p className="empty">Ask about a policy, an order, or a calculation.</p>
          )}
          {loadingThread && <p className="muted">Loading conversation…</p>}
          <MessageList messages={messages} />
          {loadingReply && activity && (
            <p className="working" role="status">
              {activity}
            </p>
          )}
          <div ref={endRef} />
        </div>
        {error && <ErrorBanner message={error} />}
        <ChatComposer value={draft} disabled={busy} onChange={setDraft} onSubmit={onSubmit} />
      </section>
    </div>
  );
}

function rememberConversation(
  response: ChatResponse,
  setConversationId: (id: string) => void,
  setConversations: (update: (current: ConversationSummary[]) => ConversationSummary[]) => void,
) {
  if (!response.conversation_id) {
    return;
  }
  const nextId = response.conversation_id;
  setConversationId(nextId);
  setConversations((current) => upsertConversation(current, nextId));
}

function applyToken(messages: ThreadMessage[], id: string, text: string, replace: boolean): ThreadMessage[] {
  if (replace && text === "") {
    return messages.filter((message) => message.id !== id);
  }
  const existing = messages.some((message) => message.id === id);
  if (!existing) {
    return [...messages, { id, role: "assistant", content: text }];
  }
  return messages.map((message) =>
    message.id === id ? { ...message, content: replace ? text : message.content + text } : message,
  );
}

function applyDone(messages: ThreadMessage[], id: string, response: ChatResponse): ThreadMessage[] {
  const next: ThreadMessage = {
    id: response.run_id ?? id,
    role: "assistant",
    content: response.answer,
    toolsUsed: response.tools_used ?? [],
    sources: response.sources ?? [],
  };
  if (!messages.some((message) => message.id === id)) {
    return [...messages, next];
  }
  return messages.map((message) => (message.id === id ? next : message));
}

function upsertConversation(rows: ConversationSummary[], id: string): ConversationSummary[] {
  const existing = rows.find((row) => row.id === id);
  const rest = rows.filter((row) => row.id !== id);
  return [{ id, created_at: existing?.created_at ?? new Date().toISOString() }, ...rest];
}
