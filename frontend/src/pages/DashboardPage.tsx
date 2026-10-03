import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import PageHeader from "../components/PageHeader";

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <>
      <PageHeader
        title={user ? `Welcome, ${user.name}` : "Dashboard"}
        description="Ask the agent, review documents, or inspect how a run was produced."
      />
      <div className="page-body">
        <div className="card-grid">
          <Link className="card" to="/chat">
            <h2>Chat</h2>
            <p>Ask a question and see which tools the agent used.</p>
          </Link>
          <Link className="card" to="/documents">
            <h2>Documents</h2>
            <p>Text and markdown the agent can search.</p>
          </Link>
          <Link className="card" to="/agent-runs">
            <h2>Agent runs</h2>
            <p>Status and final answers for executions in your organization.</p>
          </Link>
        </div>
      </div>
    </>
  );
}
