import { NavLink } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

const LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/chat", label: "Chat" },
  { to: "/documents", label: "Documents" },
  { to: "/agent-runs", label: "Agent runs" },
  { to: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const { user, signOut } = useAuth();

  return (
    <aside className="sidebar">
      <p className="brand">AgentOps AI</p>
      <nav aria-label="Main">
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} end>
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        {user && (
          <p className="sidebar-user">
            <span>{user.name}</span>
            <span>{user.role === "admin" ? "Admin" : "User"}</span>
          </p>
        )}
        <button type="button" className="sidebar-signout" onClick={signOut}>
          Sign out
        </button>
      </div>
    </aside>
  );
}
