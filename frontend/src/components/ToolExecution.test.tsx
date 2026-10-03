import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ToolExecution from "./ToolExecution";

describe("ToolExecution", () => {
  it("shows the tools the agent used", () => {
    render(<ToolExecution tools={["calculator", "search_knowledge", "calculator"]} />);

    const section = screen.getByRole("region", { name: "Agent execution" });
    expect(section).toHaveTextContent("Calculator");
    expect(section).toHaveTextContent("Knowledge Search");
    expect(screen.getAllByText("Calculator")).toHaveLength(1);
  });

  it("renders nothing when the agent did not use a tool", () => {
    render(<ToolExecution tools={[]} />);

    expect(screen.queryByRole("region", { name: "Agent execution" })).not.toBeInTheDocument();
  });
});
