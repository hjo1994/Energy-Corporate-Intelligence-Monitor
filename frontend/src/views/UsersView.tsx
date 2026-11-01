import { useCallback, useEffect, useState } from "react";
import { ApiError, fetchUsers, setUserRole } from "../api/client";
import type { AppUser } from "../api/types";

/** Everyone who signed in, and their role: approvers grant and take the approver role. */
export function UsersView() {
  const [users, setUsers] = useState<AppUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setUsers(await fetchUsers());
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? "Only approvers can manage users." : err instanceof Error ? err.message : "The users could not be loaded.");
    }
  }, []);
  useEffect(() => void load(), [load]);

  async function change(user: AppUser, role: AppUser["role"]) {
    setSaving(user.id);
    setSaveError(null);
    try {
      const saved = await setUserRole(user.id, role);
      setUsers((list) => (list ?? []).map((u) => (u.id === saved.id ? saved : u)));
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "The role could not be changed.");
    } finally {
      setSaving(null);
    }
  }

  if (error) {
    return (
      <div className="state card" role="alert">
        <p>{error}</p>
      </div>
    );
  }
  if (!users) return <p className="state" role="status">Loading the users …</p>;

  const approvers = users.filter((u) => u.role === "approver").length;
  return (
    <div className="lc">
      <header className="lc-head">
        <div>
          <h1>Users</h1>
          <p className="muted">Everyone who has signed in. Approvers see the approval inbox and decide on new ideas; users see and edit only their own use cases.</p>
        </div>
        <span className="chip active">Approvers {approvers}</span>
      </header>
      {saveError && <p className="nf-save-error" role="alert">{saveError}</p>}
      <section className="card lc-table-card" aria-label="Users">
        <table className="lc-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>E-mail</th>
              <th>Business unit</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td>
                <td>{u.email ?? "–"}</td>
                <td>{u.business_unit ?? <span className="muted">not an owner yet</span>}</td>
                <td>
                  <select
                    className="nf-input"
                    aria-label={`Role of ${u.name}`}
                    value={u.role}
                    disabled={saving === u.id}
                    onChange={(e) => void change(u, e.target.value as AppUser["role"])}
                  >
                    <option value="user">User</option>
                    <option value="approver">Approver</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
