import { expect, test, type Page, type Route } from "@playwright/test";

const user = {
  id: "8d0b6b5e-3c1a-4f2e-9a7b-1c2d3e4f5a6b",
  email: "ada@example.com",
  name: "Ada",
  role: "user",
  organization_id: "7f1c7b7e-3c2e-4a59-9d39-2b0f5c3d8a10",
};

const answer = "The result of 6 * 7 is 42.";

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

async function installApi(page: Page): Promise<{ streamBody: () => Promise<unknown> }> {
  let streamPayload: unknown;
  const payloadReady = deferred<void>();
  const releaseStream = deferred<void>();

  await page.route("**/api/v1/**", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "unexpected_test_request", message: route.request().url() },
      }),
    }),
  );
  await page.route("**/api/v1/auth/login", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ access_token: "token-1", token_type: "bearer", user }),
    }),
  );
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) }),
  );
  await page.route("**/api/v1/conversations", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/v1/chat/stream", async (route: Route) => {
    streamPayload = route.request().postDataJSON();
    payloadReady.resolve();
    await releaseStream.promise;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "Cache-Control": "no-cache" },
      body: [
        sse("status", { status: "thinking" }),
        sse("status", { status: "tool", tool: "calculator" }),
        sse("status", { status: "generating" }),
        sse("token", { text: answer, replace: false }),
        sse("done", {
          answer,
          sources: [],
          tools_used: ["calculator"],
          conversation_id: "conv-1",
          run_id: "run-1",
        }),
      ].join(""),
    });
  });

  return {
    streamBody: async () => {
      await payloadReady.promise;
      releaseStream.resolve();
      return streamPayload;
    },
  };
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test("login, ask a question, and see the tool with the final answer", async ({ page }) => {
  const api = await installApi(page);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

  await page.getByLabel("Email").fill("ada@example.com");
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Chat" }).click();

  await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("What is 6 * 7?");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByRole("status")).toHaveText("Thinking...");
  const sent = await api.streamBody();
  expect(sent).toMatchObject({ message: "What is 6 * 7?" });

  await expect(page.getByText(answer)).toBeVisible();
  const execution = page.getByRole("region", { name: "Agent execution" });
  await expect(execution).toBeVisible();
  await expect(execution).toContainText("Calculator");
  await expect(page.getByText("What is 6 * 7?")).toBeVisible();
});
