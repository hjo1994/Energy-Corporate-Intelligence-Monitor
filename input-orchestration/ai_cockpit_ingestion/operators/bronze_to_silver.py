"""Bronze-to-Silver operator: turns one extract table into silver Initiative
rows for its business unit.

Per row: normalizes status/timing/complexity (transforms.normalize), links
the config tables, estimates the four value buckets, the confidence and
delivery factors and the costs (transforms.value_heuristic), and the risk
level (transforms.risk_heuristic).

Config tables are only looked up, never written: an owner, solution type or
flagship that is not in the config is left NULL and logged, so it can be
added to the config deliberately. Every initiative gets a risk level (1-4
are always estimable, 5 is never estimated).

Each run replaces this business unit's initiatives in one transaction; the
other units' rows are untouched, so the generated DAGs can run
independently. The unit is identified via Owner.category (the data model
has no source column on Initiative), plus — for rows without a known
owner — the initiative name.
"""
from __future__ import annotations

import datetime
from collections import Counter

from airflow.sdk import BaseOperator
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import EXTRACT_TABLES, Initiative, Owner, SolutionType, ValueType
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY
from ai_cockpit_ingestion.transforms.normalize import (
    build_match_key_index,
    clean_text,
    derive_solution_complexity_score,
    derive_timing_date,
    match_catalog_name,
    normalize_status,
)
from ai_cockpit_ingestion.transforms.risk_heuristic import estimate_risk_level
from ai_cockpit_ingestion.transforms.value_heuristic import estimate_value


class BronzeToSilverOperator(BaseOperator):
    template_fields = ("db_path",)

    def __init__(self, *, source_key: str, db_path: str, **kwargs):
        super().__init__(**kwargs)
        self.source_key = source_key
        self.db_path = db_path

    def execute(self, context) -> int:
        source = SOURCES_BY_KEY[self.source_key]
        table = EXTRACT_TABLES[source.extract_table]
        engine = get_engine(self.db_path)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        unmatched: Counter[str] = Counter()

        with Session(engine) as session, session.begin():
            bronze_rows = [dict(r._mapping) for r in session.execute(select(table).order_by(table.c._SourceRow))]
            if not bronze_rows:
                raise RuntimeError(f"{source.extract_table} is empty — run RawToBronze first")

            owners = {
                (o.name, o.department or ""): o
                for o in session.scalars(select(Owner).where(Owner.category == source.business_unit))
            }
            owners_by_name = {}
            for o in owners.values():
                owners_by_name.setdefault(o.name, o)
            solution_types = {st.name: st for st in session.scalars(select(SolutionType))}
            value_types = {vt.name: vt for vt in session.scalars(select(ValueType))}
            if not solution_types or not value_types:
                raise RuntimeError("Config tables are empty — run the seed_config DAG once first")
            solution_type_index = build_match_key_index(list(solution_types))
            value_type_index = build_match_key_index(list(value_types))

            initiatives = []
            for row in bronze_rows:
                get = lambda column: row.get(column)  # noqa: E731 — absent columns read as None
                name = clean_text(get("Name"))

                owner_name, department = clean_text(get("Owner")), clean_text(get("Department"))
                owner = owners.get((owner_name, department or "")) or owners_by_name.get(owner_name)
                if owner is None and owner_name:
                    unmatched["owner"] += 1
                    self.log.warning("Owner %r (%s) of %r not in config — owner left NULL", owner_name, department, name)

                solution_type_name = match_catalog_name(
                    get("Solution Type"), canonical_names_by_match_key=solution_type_index,
                    initiative_name=name, field_label="Solution Type",
                )
                if solution_type_name is None and clean_text(get("Solution Type")):
                    unmatched["solution_type"] += 1
                value_type_name = match_catalog_name(
                    get("Flagship"), canonical_names_by_match_key=value_type_index,
                    initiative_name=name, field_label="Flagship",
                )
                if value_type_name is None and clean_text(get("Flagship")):
                    unmatched["value_type"] += 1

                stage = normalize_status(get("Status"), initiative_name=name)
                if stage == "Unknown":
                    unmatched["stage"] += 1

                value = estimate_value(
                    status=get("Status"),
                    value=get("Value"),
                    ai_layer=get("AI Layer"),
                    # Catalog spelling where it matches, else the free text.
                    solution_type=solution_type_name or get("Solution Type"),
                    flagship=value_type_name or get("Flagship"),
                    solution_feasibility=get("Solution Feasibility"),
                    complexity=get("Complexity"),
                    cost_assessment=get("High-Level Cost Assessment"),
                    description=get("Description"),
                    expected_outcome=get("Expected Outcome"),
                    added_value=get("Added Value"),
                )
                risk = estimate_risk_level(
                    name=name,
                    description=get("Description"),
                    expected_outcome=get("Expected Outcome"),
                    added_value=get("Added Value"),
                    solution_type=solution_type_name or clean_text(get("Solution Type")),
                )

                initiatives.append(
                    Initiative(
                        name=name,
                        description=clean_text(get("Description")),
                        stage=stage,
                        date_start=derive_timing_date(
                            get("Timing start"), assumed_year=config.PLANNING_YEAR,
                            initiative_name=name, field_label="Timing start",
                        ),
                        date_delivery=derive_timing_date(
                            get("Timing delivery"), assumed_year=config.PLANNING_YEAR,
                            initiative_name=name, field_label="Timing delivery",
                        ),
                        efficiency_score_eur=value.efficiency_eur,
                        quality_score_eur=value.quality_eur,
                        risk_reduction_score_eur=value.risk_reduction_eur,
                        strategic_value_score_eur=value.strategic_eur,
                        solution_complexity_score=derive_solution_complexity_score(
                            get("Solution Feasibility"), get("Complexity")
                        ),
                        confidence_score=value.confidence_score,
                        delivery_score=value.delivery_score,
                        one_time_costs=value.one_time_costs,
                        operating_costs=value.operating_costs,
                        depreciation_years=value.depreciation_years,
                        owner=owner,
                        solution_type=solution_types.get(solution_type_name) if solution_type_name else None,
                        value_type=value_types.get(value_type_name) if value_type_name else None,
                        risk_classification_id=risk.level,
                        timestamp=now,
                    )
                )

            names = [i.name for i in initiatives]
            unit_owner_ids = select(Owner.id).where(Owner.category == source.business_unit)
            deleted = session.execute(
                delete(Initiative).where(
                    or_(
                        Initiative.owner_id.in_(unit_owner_ids),
                        Initiative.owner_id.is_(None) & Initiative.name.in_(names),
                    )
                )
            ).rowcount
            session.add_all(initiatives)

        engine.dispose()
        self.log.info(
            "%s: replaced %d with %d initiatives for business unit %r",
            source.extract_table, deleted, len(initiatives), source.business_unit,
        )
        if unmatched:
            self.log.warning("Not matched to config / unknown values (left NULL or 'Unknown'): %s", dict(unmatched))
        return len(initiatives)
