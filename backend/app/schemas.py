from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.lifecycle import VALUE_DOMAINS, domain_problems
from app.user_input import RUNNING_COST_RANGES, running_cost_range


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OwnerOut(_Out):
    id: int
    name: str
    department: str | None
    category: str | None  # business unit


class TypeOut(_Out):
    id: int
    name: str
    description: str | None


class RiskClassificationRef(_Out):
    id: int
    name: str


class RiskClassificationOut(RiskClassificationRef):
    description: str | None
    derived_action: str | None


# ---------- choice lists (same as the CHECK constraints of UserActionExtracts) ----------

STAGES = ("Idea", "Exploration", "PoC", "MVP", "Implementation", "Production", "Retired", "On hold", "Cancelled", "Unknown")
STAGEGATES = ("Needs", "Scope", "Deploy", "Retire")
APPROVAL_STATUSES = ("pending", "approved", "rejected")
ESTIMATE_BASES = ("rough", "benchmark", "measured")
DELIVERY_LIKELIHOODS = ("low", "medium", "high")
EMPLOYEE_PERSONAL_DATA = ("no", "pseudonymised", "yes")
DECISIONS_ON_EMPLOYEES = ("none", "prepares", "automated")
AI_LAYERS = (
    "AI for productivity and efficiency",
    "AI for business process optimization",
    "Operational and advanced AI",
)
ENABLING_TEAMS = ("DiY", "DiY with support from DWP", "ad-hoc IT support", "NEST", "EL.AI", "data science chapter", "other")
COMPLEXITY_SOLIDITIES = ESTIMATE_BASES
EU_AI_ACT_CLASSES = ("banned", "high-risk", "transparency", "minimal")
EU_AI_ACT_ROLES = ("provider", "deployer", "consumer")
WORKS_COUNCIL_RISK_CLASSES = ("hi", "med-de", "med", "med-lo", "lo")
CAPABILITY_DIRECTIONS = ("providing", "consuming")
APPLICABLE_TO = ("ETB", "50Hertz", "Windgrid", "EGI", "Group")  # several possible, sent comma-separated

Processing = Literal["pending", "changes_pending", "not_assessed", "assessed"]


# ---------- dashboard ----------


class InitiativeOut(_Out):
    """One use case in the dashboard. `id` is the UseCaseID (stable across
    versions); a use case created in the UI and not processed yet has
    id = −user_input_id and processing "pending"."""

    id: int
    use_case_id: int | None = None
    version_id: int | None = None
    name: str
    description: str | None
    stage: str | None
    date_start: datetime | None
    date_delivery: datetime | None
    # value buckets and discount factors (estimates, EUR per year)
    efficiency_score_eur: float | None
    quality_score_eur: float | None
    risk_reduction_score_eur: float | None
    strategic_value_score_eur: float | None
    confidence_score: float | None
    delivery_score: float | None
    solution_complexity_score: float | None
    one_time_costs: float | None
    running_costs: float | None
    operating_costs: float | None = None  # deprecated: same as running_costs, until the UI has switched
    depreciation_years: int | None
    hypothetical_value_eur: float | None
    potential_value_eur: float | None  # gold PotentialValue (provisional until assessed)
    realized_value_eur: float | None = None  # gold RealizedValue
    annual_cost_eur: float | None
    owner: OwnerOut | None
    lead: OwnerOut | None = None
    solution_type: TypeOut | None
    value_type: TypeOut | None
    risk_classification: RiskClassificationRef | None
    ai_layer: str | None = None
    approval_status: Literal["pending", "approved", "rejected"] | None = None  # NULL: imported from a sheet
    # one date per stage gate: up to today = passed, later = planned (see app/lifecycle.py)
    needs_gate_date: datetime | None = None
    scope_gate_date: datetime | None = None
    deploy_gate_date: datetime | None = None
    retire_gate_date: datetime | None = None
    last_gate: Literal[STAGEGATES] | None = None  # type: ignore[valid-type]  # latest gate passed by today
    is_active: bool
    # "active"/"inactive" (soft-deleted) or "pending" (created in the UI, not processed yet)
    status: Literal["active", "inactive", "pending"] = "active"
    processing: Processing = "assessed"
    provisional: bool = False  # potential value and risk level not from gold yet
    user_input_id: int | None = None
    business_transaction_id: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_state(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "processing" not in data:
            return data
        state = dict(data)
        state["approval_status"] = state.get("approval_status", state.get("status"))
        state["status"] = ("pending" if state["processing"] == "pending"
                           else "active" if state["is_active"] else "inactive")
        state["operating_costs"] = state.get("running_costs")
        state["user_input_id"] = state.get("user_action_id")
        return state


class InitiativePage(BaseModel):
    items: list[InitiativeOut]
    total: int
    limit: int
    offset: int


class StageCount(BaseModel):
    stage: str
    count: int


class RiskClassificationCount(BaseModel):
    id: int
    name: str
    count: int


class BusinessUnitCount(BaseModel):
    name: str | None
    count: int


class Summary(BaseModel):
    total: int
    by_stage: list[StageCount]
    by_risk_classification: list[RiskClassificationCount]
    with_potential_value: int
    without_potential_value: int  # incl. use cases not assessed yet
    not_assessed: int
    total_potential_value_eur: float | None
    average_potential_value_eur: float | None
    total_realized_value_eur: float | None
    total_hypothetical_value_eur: float | None
    total_annual_cost_eur: float | None
    average_solution_complexity_score: float | None
    without_owner: int


# ---------- use cases (forms, my use cases, approvals) ----------


class Form2Progress(BaseModel):
    filled: int
    total: int


class UseCaseDetail(InitiativeOut):
    """Everything of forms 1 and 2, the gold values and what the signed-in user may do."""

    comment: str | None
    measured_benefits: float | None
    actual_costs: float | None
    running_cost_range: str | None = None
    employee_personal_data: str | None
    performance_or_behaviour_control: bool | None
    decisions_on_employees: str | None
    profiling_of_individuals: bool | None
    changes_employee_workflows: bool | None
    prohibited_practice: bool | None
    enabling_team: str | None
    complexity_solidity: str | None
    strategic_kpis: str | None
    tactical_kpis: str | None
    value_domain: str | None
    autonomy_level: str | None
    eu_ai_act_class: str | None
    eu_ai_act_role: str | None
    works_council_risk_class: str | None
    target_user_groups: str | None
    applicable_to: str | None
    capability_direction: str | None
    safety_component: bool | None
    works_council_approved_at: datetime | None
    expected_users: int | None
    # the entered value drivers, merged over all actions (empty for sheet use cases)
    drivers: dict[str, Any] = {}
    submitted_by: str | None
    submitted_at: datetime | None
    changed_by: str | None
    updated_at: datetime | None
    assessed_version_id: int | None
    assessed_at: datetime | None
    pending_action_ids: list[int]
    revision: str  # send back as base_revision when saving
    form2_progress: Form2Progress
    # what does not fit between stage and gate dates (e.g. a sheet use case in Production without dates)
    stage_problems: list[str] = []
    stage_floor: str | None = None  # the stage given in form 1; the stage cannot go below it
    todos: list[str] = []
    can_edit: bool = False
    can_decide: bool = False

    @model_validator(mode="before")
    @classmethod
    def _cost_range(cls, data: Any) -> Any:
        if isinstance(data, dict) and "running_cost_range" not in data:
            entered = (data.get("drivers") or {}).get("operating_costs")
            data = {**data, "running_cost_range": running_cost_range(entered)}
        return data


class MyUseCase(_Out):
    id: int
    name: str
    approval_status: str | None
    stage: str | None
    needs_gate_date: datetime | None = None
    scope_gate_date: datetime | None = None
    deploy_gate_date: datetime | None = None
    retire_gate_date: datetime | None = None
    last_gate: str | None = None
    stage_problems: list[str] = []
    comment: str | None
    potential_value_eur: float | None
    risk_classification: RiskClassificationRef | None
    processing: Processing
    provisional: bool
    form2_progress: Form2Progress
    roles: list[Literal["submitter", "owner", "lead"]]
    todos: list[str]
    updated_at: datetime | None
    can_edit: bool


class ApprovalItem(_Out):
    id: int
    name: str
    description: str | None
    owner: OwnerOut | None
    value_type: TypeOut | None
    ai_layer: str | None
    submitted_by: str | None
    submitted_at: datetime | None
    potential_value_eur: float | None
    hypothetical_value_eur: float | None
    annual_cost_eur: float | None
    solution_complexity_score: float | None
    risk_classification: RiskClassificationRef | None
    processing: Processing
    can_decide: bool  # false while the idea is still being processed (id < 0) or a decision is pending


class SimilarUseCase(_Out):
    id: int
    name: str
    stage: str | None
    owner: OwnerOut | None
    score: float  # 0-1, word overlap of name and description


# ---------- input ----------

Quarter = Annotated[str, StringConstraints(pattern=r"^Q[1-4] \d{4}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Count = Annotated[float, Field(ge=0)]
Share = Annotated[float, Field(ge=0, le=1)]  # a percentage divided by 100
CostRange = Literal[tuple(RUNNING_COST_RANGES)]  # type: ignore[valid-type]

# Value levers and their drivers; a create needs at least one complete lever.
LEVERS = {
    "efficiency": ("cases_per_year", "hours_saved_per_case"),
    "quality": ("cases_per_year", "error_rate_before", "errors_avoided", "cost_per_error"),
    "risk_reduction": ("risk_events_per_year", "events_avoided", "cost_per_event"),
    "speed": ("delay_events_per_year", "cost_of_delay_per_event", "lead_time_saved"),
}


class _Form1Values(BaseModel):
    """Value drivers of form 1 (shares as fractions 0-1)."""

    model_config = ConfigDict(extra="forbid")

    cases_per_year: Count | None = None
    hours_saved_per_case: Count | None = None
    error_rate_before: Share | None = None
    errors_avoided: Share | None = None
    cost_per_error: Count | None = None
    risk_events_per_year: Count | None = None
    events_avoided: Share | None = None
    cost_per_event: Count | None = None
    delay_events_per_year: Count | None = None
    cost_of_delay_per_event: Count | None = None
    lead_time_saved: Share | None = None

    @model_validator(mode="after")
    def _in_domain(self) -> "_Form1Values":
        # every number of form 1 is one of the values of its domain (app/lifecycle.py)
        problems = domain_problems({f: getattr(self, f, None) for f in VALUE_DOMAINS})
        if problems:
            raise ValueError("; ".join(problems))
        return self


class _GateDates(BaseModel):
    """One date per stage gate; whether they fit the stage is checked by the API (it needs today)."""

    needs_gate_date: date | None = None
    scope_gate_date: date | None = None
    deploy_gate_date: date | None = None
    retire_gate_date: date | None = None


class InitiativeIn(_GateDates, _Form1Values):
    """Form 1, a new AI idea; the same rules as the CHECK constraints of
    UserActionExtracts, plus: at least one complete value lever, numbers from
    their domains, gate dates that fit the stage. The AI layer replaces the
    solution type (now form 2), running costs come as a range."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Text
    # The signed-in user becomes the owner (app/users.py); a user without an owner row
    # yet names their business unit once (Owner.Category of the new owner).
    business_unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    value_type_id: int
    ai_layer: Literal[AI_LAYERS]  # type: ignore[valid-type]
    stage: Literal[STAGES]  # type: ignore[valid-type]
    date_start: Quarter | None = None
    date_delivery: Quarter | None = None

    estimate_basis: Literal[ESTIMATE_BASES]  # type: ignore[valid-type]
    delivery_likelihood: Literal[DELIVERY_LIKELIHOODS]  # type: ignore[valid-type]
    solution_complexity_score: Annotated[int, Field(ge=1, le=9)]
    one_time_costs: Count
    running_cost_range: CostRange

    employee_personal_data: Literal[EMPLOYEE_PERSONAL_DATA]  # type: ignore[valid-type]
    performance_or_behaviour_control: bool
    decisions_on_employees: Literal[DECISIONS_ON_EMPLOYEES]  # type: ignore[valid-type]
    profiling_of_individuals: bool
    changes_employee_workflows: bool
    prohibited_practice: bool

    @model_validator(mode="after")
    def _one_complete_lever(self) -> "InitiativeIn":
        if not any(all(getattr(self, f) is not None for f in fields) for fields in LEVERS.values()):
            raise ValueError("At least one value lever needs all of its drivers")
        return self


FORM1_FIELDS = (
    "description", "business_unit", "value_type_id", "ai_layer", "stage", "date_start", "date_delivery",
    *(f for fields in LEVERS.values() for f in fields), "estimate_basis", "delivery_likelihood",
    "solution_complexity_score", "one_time_costs", "running_cost_range",
    "employee_personal_data", "performance_or_behaviour_control", "decisions_on_employees",
    "profiling_of_individuals", "changes_employee_workflows", "prohibited_practice",
)
FORM2_INPUT_FIELDS = (
    "lead_id", "solution_type_id", "enabling_team", "complexity_solidity", "strategic_kpis", "tactical_kpis",
    "value_domain", "autonomy_level", "eu_ai_act_class", "eu_ai_act_role", "works_council_risk_class",
    "target_user_groups", "applicable_to", "capability_direction", "safety_component",
    "works_council_approved_at", "expected_users",
    "measured_benefits", "actual_capex", "actual_opex",
)


class UseCasePatch(_GateDates, _Form1Values):
    """A partial update (form 2, stage and gate dates): only the fields sent
    count. Name and business unit never change; description and the cost
    estimates of form 1 only while a rejected idea is revised. The stage cannot
    go below the one given in form 1."""

    base_revision: str  # `revision` of the state the user edited; a newer one -> 409

    description: Text | None = None
    owner_id: int | None = None  # within the same business unit
    value_type_id: int | None = None
    ai_layer: Literal[AI_LAYERS] | None = None  # type: ignore[valid-type]
    stage: Literal[STAGES] | None = None  # type: ignore[valid-type]
    date_start: Quarter | None = None
    date_delivery: Quarter | None = None
    estimate_basis: Literal[ESTIMATE_BASES] | None = None  # type: ignore[valid-type]
    delivery_likelihood: Literal[DELIVERY_LIKELIHOODS] | None = None  # type: ignore[valid-type]
    solution_complexity_score: Annotated[int, Field(ge=1, le=9)] | None = None
    one_time_costs: Count | None = None
    running_cost_range: CostRange | None = None
    employee_personal_data: Literal[EMPLOYEE_PERSONAL_DATA] | None = None  # type: ignore[valid-type]
    performance_or_behaviour_control: bool | None = None
    decisions_on_employees: Literal[DECISIONS_ON_EMPLOYEES] | None = None  # type: ignore[valid-type]
    profiling_of_individuals: bool | None = None
    changes_employee_workflows: bool | None = None
    prohibited_practice: bool | None = None

    # form 2
    lead_id: int | None = None
    solution_type_id: int | None = None
    enabling_team: Literal[ENABLING_TEAMS] | None = None  # type: ignore[valid-type]
    complexity_solidity: Literal[COMPLEXITY_SOLIDITIES] | None = None  # type: ignore[valid-type]
    strategic_kpis: ShortText | None = None
    tactical_kpis: ShortText | None = None
    value_domain: ShortText | None = None
    autonomy_level: ShortText | None = None
    eu_ai_act_class: Literal[EU_AI_ACT_CLASSES] | None = None  # type: ignore[valid-type]
    eu_ai_act_role: Literal[EU_AI_ACT_ROLES] | None = None  # type: ignore[valid-type]
    works_council_risk_class: Literal[WORKS_COUNCIL_RISK_CLASSES] | None = None  # type: ignore[valid-type]
    target_user_groups: ShortText | None = None
    applicable_to: list[Literal[APPLICABLE_TO]] | None = None  # type: ignore[valid-type]
    capability_direction: Literal[CAPABILITY_DIRECTIONS] | None = None  # type: ignore[valid-type]
    safety_component: bool | None = None
    works_council_approved_at: date | None = None
    expected_users: Annotated[int, Field(ge=0)] | None = None
    measured_benefits: Count | None = None  # EUR, total to date
    actual_capex: Count | None = None  # EUR, spent to date
    actual_opex: Count | None = None

    resubmit: bool = False  # a rejected idea goes back to "pending"

    @model_validator(mode="before")
    @classmethod
    def _immutable(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field in ("name", "business_unit"):
                if field in data:
                    raise ValueError(f"{field} cannot be changed after the idea was submitted")
        return data


class DecisionIn(BaseModel):
    """The approver's decision on a pending idea."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    lead_id: int | None = None  # required to approve; approving passes the needs gate (today, unless dated)
    comment: ShortText | None = None  # required to reject
    base_revision: str | None = None

    @model_validator(mode="after")
    def _required(self) -> "DecisionIn":
        if self.decision == "approve" and self.lead_id is None:
            raise ValueError("Approving needs a use case lead (lead_id)")
        if self.decision == "reject" and not self.comment:
            raise ValueError("Rejecting needs a comment")
        return self


class AppUserOut(_Out):
    """A signed-in user on the Users page."""

    id: int
    name: str
    email: str | None
    role: Literal["user", "approver"]
    is_active: bool
    owner_id: int | None = None
    business_unit: str | None = None


class RoleIn(BaseModel):
    role: Literal["user", "approver"]
