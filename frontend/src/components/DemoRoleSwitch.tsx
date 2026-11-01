import { chooseDemoApprover } from "../shared/api/demoRole";
import { useApp } from "../store";

/**
 * For demo presenters only (the backend says who): switch between the own normal rights and
 * approver rights, e.g. to submit an idea and then approve it in a demo with one SSO account.
 */
export function DemoRoleSwitch({ onSwitch = () => window.location.reload() }: { onSwitch?: () => void }) {
  const { rights } = useApp();
  if (!rights.demoPresenter) return null;
  const approver = rights.demoApprover === true;
  return (
    <div className="view-as" role="radiogroup" aria-label="Demo role">
      {[
        { on: false, label: "Normal user" },
        { on: true, label: "Approver (demo)" },
      ].map((o) => (
        <button
          key={o.label}
          type="button"
          role="radio"
          aria-checked={approver === o.on}
          className={approver === o.on ? "view-as-opt view-as-current" : "view-as-opt"}
          onClick={() => {
            if (approver === o.on) return;
            chooseDemoApprover(o.on);
            onSwitch();
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
