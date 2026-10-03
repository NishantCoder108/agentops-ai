import { useAuth } from "../auth/AuthContext";
import Button from "../components/Button";
import PageHeader from "../components/PageHeader";

export default function SettingsPage() {
  const { user, signOut } = useAuth();

  return (
    <>
      <PageHeader title="Settings" description="Account details for this browser session." />
      <div className="page-body">
        {user && (
          <dl className="details">
            <div>
              <dt>Name</dt>
              <dd>{user.name}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{user.role === "admin" ? "Admin" : "User"}</dd>
            </div>
          </dl>
        )}
        <Button variant="ghost" onClick={signOut}>
          Sign out
        </Button>
      </div>
    </>
  );
}
