import PageHeader from "../components/PageHeader";

export default function AgentRunsPage() {
  return (
    <>
      <PageHeader
        title="Agent runs"
        description="Admins can review each run in the organization, including its status and final answer."
      />
      <div className="page-body">
        <p className="panel">No runs are listed here yet.</p>
      </div>
    </>
  );
}
