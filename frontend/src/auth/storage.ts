export const TOKEN_KEY = "agentops.access_token";
export const UNAUTHORIZED_EVENT = "agentops-unauthorized";

export function readToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function writeToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    return;
  }
  localStorage.removeItem(TOKEN_KEY);
}
