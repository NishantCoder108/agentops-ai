import type { Source } from "../../api/types";
import ToolExecution from "../ToolExecution";

export type ThreadMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolsUsed?: string[];
  sources?: Source[];
};

export default function MessageList({ messages }: { messages: ThreadMessage[] }) {
  return (
    <div className="messages">
      {messages.map((message) =>
        message.role === "user" ? (
          <article key={message.id} className="message message-user">
            <p>{message.content}</p>
          </article>
        ) : (
          <article key={message.id} className="message message-assistant">
            <ToolExecution tools={message.toolsUsed ?? []} />
            <p>{message.content}</p>
            {message.sources && message.sources.length > 0 && (
              <ul className="sources">
                {message.sources.map((source) => (
                  <li key={`${source.document_id}-${source.relevant_excerpt}`}>
                    <span>{source.document_name}</span>
                    {source.relevant_excerpt}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ),
      )}
    </div>
  );
}
