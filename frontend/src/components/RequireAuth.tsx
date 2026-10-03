import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export default function RequireAuth() {
  const { status } = useAuth();
  if (status === "loading") {
    return <p className="boot">Loading…</p>;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
