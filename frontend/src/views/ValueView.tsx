import { BreakEvenMap } from "../components/BreakEvenMap";
import { BusinessUnitChips, StageChips } from "../components/FilterChips";
import { ValueBridge } from "../components/ValueBridge";
import { ValueRoadmap } from "../components/ValueRoadmap";
import { useApp } from "../store";

export function ValueView() {
  const { all, visible } = useApp();
  return (
    <>
      <div className="filter-row">
        <BusinessUnitChips all={all} />
        <StageChips all={all} />
      </div>
      <p className="muted value-intro">
        All values are heuristic estimates (heuristic v2) in € per year, not business cases.
      </p>
      <ValueBridge items={visible} />
      <BreakEvenMap items={visible} />
      <ValueRoadmap items={visible} />
    </>
  );
}
