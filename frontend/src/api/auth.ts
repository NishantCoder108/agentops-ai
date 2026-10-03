import type { AuthResponse, User } from "./types";
import { apiRequest } from "./client";

export function login(email: string, password: string): Promise<AuthResponse> {
  return apiRequest<AuthResponse>("/api/v1/auth/login", {
    method: "POST",
    auth: false,
    body: { email, password },
  });
}

export function currentUser(): Promise<User> {
  return apiRequest<User>("/api/v1/auth/me");
}
