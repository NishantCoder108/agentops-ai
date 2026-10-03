import type { ConversationSummary } from "../../api/types";

type Props = {
  conversations: ConversationSummary[];
  selectedId: string | null;
  onSelect: (conversationId: string) => void;
};

export default function ConversationList({ conversations, selectedId, onSelect }: Props) {
  if (conversations.length === 0) {
    return <p className="muted history-empty">No conversations yet.</p>;
  }

  return (
    <ul className="history-list">
      {conversations.map((conversation) => (
        <li key={conversation.id}>
          <button
            type="button"
            className={conversation.id === selectedId ? "history-item is-selected" : "history-item"}
            aria-current={conversation.id === selectedId ? "true" : undefined}
            onClick={() => onSelect(conversation.id)}
          >
            {formatConversationTime(conversation.created_at)}
          </button>
        </li>
      ))}
    </ul>
  );
}

function formatConversationTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Conversation";
  }
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
