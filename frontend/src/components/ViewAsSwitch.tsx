import { useApp } from "../store";

/**
 * For approvers and admins: look at the app as a normal user and back, e.g. to show both
 * sides in a demo with one SSO account. Only the view changes; it can take rights away,
 * never add them.
 */
export function ViewAsSwitch() {
  const { realRights, viewAsSubmitter, setViewAsSubmitter } = useApp();
  if (!realRights.canApprove) return null;
  const role = realRights.canAdmin ? "Admin" : "Approver";
  return (
    <div className="view-as" role="radiogroup" aria-label="View as">
      <span className="view-as-label">View as</span>
      {[
        { on: false, label: role },
        { on: true, label: "Submitter" },
      ].map((o) => (
        <button
          key={o.label}
          type="button"
          role="radio"
          aria-checked={viewAsSubmitter === o.on}
          className={viewAsSubmitter === o.on ? "view-as-opt view-as-current" : "view-as-opt"}
          onClick={() => setViewAsSubmitter(o.on)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
