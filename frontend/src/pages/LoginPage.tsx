import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Button from "../components/Button";
import ErrorBanner from "../components/ErrorBanner";
import TextField from "../components/TextField";

export default function LoginPage() {
  const { status, signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "loading") {
    return <p className="boot">Loading…</p>;
  }
  if (status === "authenticated") {
    return <Navigate to="/chat" replace />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email, password);
      navigate("/chat");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={onSubmit}>
        <p className="brand-mark">AgentOps AI</p>
        <h1>Sign in</h1>
        <p className="muted">Use the account for your organization.</p>
        {error && <ErrorBanner message={error} />}
        <TextField
          label="Email"
          name="email"
          type="email"
          autoComplete="username"
          value={email}
          disabled={submitting}
          onChange={setEmail}
        />
        <TextField
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          disabled={submitting}
          onChange={setPassword}
        />
        <Button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}
