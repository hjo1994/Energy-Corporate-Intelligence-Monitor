import { useEffect, useState } from "react";

import { chooseDevUser, fetchDevUsers, fetchSignedInName, type DevUser } from "./devUsers";

/** Local demo: switch between the backend's personas (only shown when it has some). */
export function DevUserSwitch({ onSwitch = () => window.location.reload() }: { onSwitch?: () => void }) {
  const [users, setUsers] = useState<DevUser[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchDevUsers(), fetchSignedInName()]).then(([list, name]) => {
      if (cancelled) return;
      setUsers(list);
      setCurrent(list.find((u) => u.name === name)?.email ?? list[0]?.email ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  if (users.length === 0) return null;
  return (
    <label className="dev-user">
      <span className="dev-user-label">Demo user</span>
      <select
        value={current ?? ""}
        onChange={(e) => {
          chooseDevUser(e.target.value);
          setCurrent(e.target.value);
          onSwitch();
        }}
      >
        {users.map((u) => (
          <option key={u.email} value={u.email}>
            {u.name} ({u.role})
          </option>
        ))}
      </select>
    </label>
  );
}
