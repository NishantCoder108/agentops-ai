import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import LoginPage from "./LoginPage";

const user = {
  id: "user-1",
  email: "ada@example.com",
  name: "Ada",
  role: "user",
  organization_id: "org-1",
};

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/chat" element={<h1>Chat</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/auth/login")) {
          const body = JSON.parse(String(init?.body)) as { password?: string };
          if (body.password !== "correct-horse-battery") {
            return new Response(
              JSON.stringify({
                error: { code: "invalid_credentials", message: "Invalid email or password" },
              }),
              { status: 401, headers: { "Content-Type": "application/json" } },
            );
          }
          return new Response(
            JSON.stringify({ access_token: "token-1", token_type: "bearer", user }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.endsWith("/api/v1/auth/me")) {
          return new Response(JSON.stringify(user), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response("not found", { status: 404 });
      }),
    );
  });

  it("opens chat after a valid sign-in", async () => {
    const actor = userEvent.setup();
    renderLogin();

    await actor.type(screen.getByLabelText("Email"), "ada@example.com");
    await actor.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await actor.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Chat" })).toBeInTheDocument();
  });

  it("shows the API error when the password is wrong", async () => {
    const actor = userEvent.setup();
    renderLogin();

    await actor.type(screen.getByLabelText("Email"), "ada@example.com");
    await actor.type(screen.getByLabelText("Password"), "wrong-password");
    await actor.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
