import PageHeader from "../components/PageHeader";

export default function DocumentsPage() {
  return (
    <>
      <PageHeader
        title="Documents"
        description="Admins upload text and markdown files. The agent searches those passages when it answers."
      />
      <div className="page-body">
        <p className="panel">No documents are listed here yet.</p>
      </div>
    </>
  );
}
