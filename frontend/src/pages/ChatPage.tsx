import { useEffect, useRef, useState, type FormEvent } from "react";

import { errorMessage } from "../api/client";
import { getConversation, listConversations, sendMessage } from "../api/chat";
import type { ConversationSummary } from "../api/types";
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
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);

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
  }, [messages, loadingReply]);

  function startNewChat() {
    requestSeq.current += 1;
    setConversationId(null);
    setMessages([]);
    setError(null);
    setLoadingReply(false);
    setLoadingThread(false);
  }

  async function openConversation(id: string) {
    const seq = ++requestSeq.current;
    setConversationId(id);
    setError(null);
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
    const seq = ++requestSeq.current;
    setDraft("");
    setError(null);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", content: text }]);
    setLoadingReply(true);
    try {
      const response = await sendMessage(text, conversationId);
      if (requestSeq.current !== seq) {
        return;
      }
      if (response.conversation_id) {
        const nextId = response.conversation_id;
        setConversationId(nextId);
        setConversations((current) => upsertConversation(current, nextId));
      }
      setMessages((current) => [
        ...current,
        {
          id: response.run_id ?? crypto.randomUUID(),
          role: "assistant",
          content: response.answer,
          toolsUsed: response.tools_used ?? [],
          sources: response.sources ?? [],
        },
      ]);
    } catch (err) {
      if (requestSeq.current === seq) {
        setError(errorMessage(err));
      }
    } finally {
      if (requestSeq.current === seq) {
        setLoadingReply(false);
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
          {loadingReply && (
            <p className="working" role="status">
              Working…
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

function upsertConversation(rows: ConversationSummary[], id: string): ConversationSummary[] {
  const existing = rows.find((row) => row.id === id);
  const rest = rows.filter((row) => row.id !== id);
  return [{ id, created_at: existing?.created_at ?? new Date().toISOString() }, ...rest];
}
