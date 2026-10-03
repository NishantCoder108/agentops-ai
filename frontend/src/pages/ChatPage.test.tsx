import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { listConversations, streamMessage, type StreamHandlers } from "../api/chat";
import ChatPage from "./ChatPage";

vi.mock("../api/chat", () => ({
  listConversations: vi.fn(),
  getConversation: vi.fn(),
  streamMessage: vi.fn(),
}));

describe("ChatPage", () => {
  beforeEach(() => {
    vi.mocked(listConversations).mockResolvedValue([]);
    vi.mocked(streamMessage).mockReset();
  });

  it("shows tool progress, the final answer, and the agent execution", async () => {
    const actor = userEvent.setup();
    let handlers: StreamHandlers | undefined;
    let finish: () => void = () => {};
    vi.mocked(streamMessage).mockImplementation((_message, _conversationId, next) => {
      handlers = next;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    });

    render(<ChatPage />);
    expect(await screen.findByText("Ask about a policy, an order, or a calculation.")).toBeInTheDocument();

    await actor.type(screen.getByLabelText("Message"), "What is 6 * 7?");
    await actor.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Thinking...");
    expect(screen.getByText("What is 6 * 7?")).toBeInTheDocument();

    handlers?.onStatus("tool", "calculator");
    expect(await screen.findByRole("status")).toHaveTextContent("Calling Calculator...");

    handlers?.onStatus("generating", null);
    expect(await screen.findByRole("status")).toHaveTextContent("Generating response...");

    handlers?.onToken("The result of 6 * 7 is 42.", false);
    handlers?.onDone({
      answer: "The result of 6 * 7 is 42.",
      sources: [],
      tools_used: ["calculator"],
      conversation_id: "conv-1",
      run_id: "run-1",
    });
    finish();

    expect(await screen.findByText("The result of 6 * 7 is 42.")).toBeInTheDocument();
    const execution = screen.getByRole("region", { name: "Agent execution" });
    expect(execution).toHaveTextContent("Calculator");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(streamMessage).toHaveBeenCalledWith(
      "What is 6 * 7?",
      null,
      expect.any(Object),
      expect.any(AbortSignal),
    );
  });

  it("shows the API error and drops a partial reply when the stream fails", async () => {
    const actor = userEvent.setup();
    vi.mocked(streamMessage).mockRejectedValue(
      new ApiError(429, "rate_limited", "Too many chat requests. Try again in 60 seconds."),
    );

    render(<ChatPage />);
    await screen.findByText("Ask about a policy, an order, or a calculation.");
    await actor.type(screen.getByLabelText("Message"), "Hello");
    await actor.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many chat requests. Try again in 60 seconds.",
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Agent execution" })).not.toBeInTheDocument();
  });
});
