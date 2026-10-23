"""Bronze-to-Silver operator: upserts one extract table's latest load into the
silver Initiative rows of its business unit.

Per row: normalizes status/timing/complexity (transforms.normalize), links
the config tables, estimates the four value buckets, the confidence and
delivery factors and the costs (transforms.value_heuristic), and the risk
level (transforms.risk_heuristic).

Config tables are only looked up, never written: an owner, solution type or
flagship that is not in the config is left NULL and logged, so it can be
added to the config deliberately. Every initiative gets a risk level (1-4
are always estimable, 5 is never estimated).

Upsert (one BusinessTransaction per run, see transforms.upsert_keys):

- key_hash unknown                          -> insert (new ID)
- key_hash known, row_hash differs or row inactive -> update in place (ID kept)
- key_hash known, row_hash equal            -> unchanged, nothing written
- force=True                                -> every known key is updated
- the same key twice in one load: same row_hash -> taken once (warning);
  different row_hash -> conflict, neither row is taken, the existing silver
  row (if any) stays as it is
- active row of this extract whose key is missing from the load -> is_active = False

Inserted, updated and deactivated rows point to the new BusinessTransaction.
"Rows of this extract" are those whose last BusinessTransaction read the same
extract table, so the generated DAGs never touch each other's rows.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from airflow.models.baseoperator import BaseOperator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.lineage import STATUS_SUCCESS, latest_bronze_load, mark_failed, start_transaction, utcnow
from ai_cockpit_ingestion.models import (
    EXTRACT_TABLES,
    KIND_BRONZE_TO_SILVER,
    BusinessTransaction,
    Initiative,
    Owner,
    SolutionType,
    ValueType,
)
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY
from ai_cockpit_ingestion.transforms.normalize import (
    build_match_key_index,
    clean_text,
    derive_solution_complexity_score,
    derive_timing_date,
    match_catalog_name,
    normalize_stage,
)
from ai_cockpit_ingestion.transforms.risk_heuristic import estimate_risk_level
from ai_cockpit_ingestion.transforms.upsert_keys import key_hash, row_hash, row_hash_columns
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
        force = bool((context.get("params") or {}).get("force", False))
        engine = get_engine(self.db_path)

        with Session(engine) as session:
            load = latest_bronze_load(session, source.extract_table)
            if load is None:
                raise RuntimeError(f"{source.extract_table} has no successful load — run RawToBronze first")
            load_id, source_file, load_timestamp = load.id, load.source_file, load.load_timestamp

        transaction_id = start_transaction(
            engine,
            kind=KIND_BRONZE_TO_SILVER,
            extract_table=source.extract_table,
            business_unit=source.business_unit,
            source_file=source_file,
            load_timestamp=load_timestamp,
            source_business_transaction_id=load_id,
            force=force,
        )
        try:
            with Session(engine) as session, session.begin():
                bronze_rows = [
                    dict(r._mapping)
                    for r in session.execute(
                        select(table).where(table.c._BusinessTransactionId == load_id).order_by(table.c._SourceRow)
                    )
                ]
                counts = self._upsert(session, source, bronze_rows, transaction_id, force)
                session.execute(
                    update(BusinessTransaction)
                    .where(BusinessTransaction.id == transaction_id)
                    .values(status=STATUS_SUCCESS, finished_at=utcnow(), rows_read=len(bronze_rows), **counts)
                )
        except Exception as error:
            mark_failed(engine, transaction_id, error)
            raise
        finally:
            engine.dispose()

        self.log.info(
            "%s: business transaction %d (bronze load %d, force=%s) for business unit %r: %s",
            source.extract_table, transaction_id, load_id, force, source.business_unit, counts,
        )
        return transaction_id

    def _upsert(self, session: Session, source, bronze_rows: list[dict], transaction_id: int, force: bool) -> dict:
        counts = {"inserted": 0, "updated": 0, "unchanged": 0, "deactivated": 0, "conflicts": 0}
        now = utcnow()
        hash_columns = row_hash_columns(source.columns)

        # Group the load by key; a key may occur more than once.
        by_key: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for row in bronze_rows:
            by_key[key_hash(source.business_unit, row.get("Name"))].append((row_hash(row, hash_columns), row))

        to_apply: dict[str, tuple[str, dict]] = {}
        for key, entries in by_key.items():
            rows_txt = ", ".join(f"row {r['_SourceRow']}" for _, r in entries)
            if len({h for h, _ in entries}) == 1:
                if len(entries) > 1:
                    self.log.warning(
                        "%r occurs %d times with identical content (%s) — taken once",
                        entries[0][1].get("Name"), len(entries), rows_txt,
                    )
                to_apply[key] = entries[0]
            else:
                counts["conflicts"] += 1
                self.log.error(
                    "Conflict: %r occurs %d times with different content (%s) — not taken, "
                    "existing silver row left unchanged", entries[0][1].get("Name"), len(entries), rows_txt,
                )

        existing = {
            i.key_hash: i
            for i in session.scalars(select(Initiative).where(Initiative.key_hash.in_(list(by_key))))
        }
        lookups = _Lookups(session, source.business_unit)
        unmatched: Counter[str] = Counter()

        for key, (digest, row) in to_apply.items():
            current = existing.get(key)
            if current is not None and current.is_active and current.row_hash == digest and not force:
                counts["unchanged"] += 1
                continue
            fields = _silver_fields(row, lookups, unmatched)
            if current is None:
                session.add(
                    Initiative(
                        **fields, key_hash=key, row_hash=digest, is_active=True,
                        business_transaction_id=transaction_id, timestamp=now,
                    )
                )
                counts["inserted"] += 1
            else:
                for name, value in fields.items():
                    setattr(current, name, value)
                current.row_hash = digest
                current.is_active = True
                current.business_transaction_id = transaction_id
                current.timestamp = now
                counts["updated"] += 1

        # Soft delete: active rows of this extract that the load no longer has.
        # Conflicting keys are still present in the source, so they are kept.
        previous_transactions = select(BusinessTransaction.id).where(
            BusinessTransaction.kind == KIND_BRONZE_TO_SILVER,
            BusinessTransaction.extract_table == source.extract_table,
        )
        for row in session.scalars(
            select(Initiative).where(
                Initiative.is_active.is_(True), Initiative.business_transaction_id.in_(previous_transactions)
            )
        ):
            if row.key_hash not in by_key:
                row.is_active = False
                row.business_transaction_id = transaction_id
                row.timestamp = now
                counts["deactivated"] += 1

        if unmatched:
            self.log.warning("Not matched to config / unknown values (left NULL or 'Unknown'): %s", dict(unmatched))
        return counts


class _Lookups:
    """Config tables of one business unit, loaded once per run."""

    def __init__(self, session: Session, business_unit: str):
        self.owners = {
            (o.name, o.department or ""): o.id
            for o in session.scalars(select(Owner).where(Owner.category == business_unit))
        }
        self.owners_by_name: dict[str, int] = {}
        for (name, _), owner_id in self.owners.items():
            self.owners_by_name.setdefault(name, owner_id)
        self.solution_types = {st.name: st.id for st in session.scalars(select(SolutionType))}
        self.value_types = {vt.name: vt.id for vt in session.scalars(select(ValueType))}
        if not self.solution_types or not self.value_types:
            raise RuntimeError("Config tables are empty — run the seed_config DAG once first")
        self.solution_type_index = build_match_key_index(list(self.solution_types))
        self.value_type_index = build_match_key_index(list(self.value_types))


def _silver_fields(row: dict, lookups: _Lookups, unmatched: Counter) -> dict:
    get = row.get  # absent columns read as None
    name = clean_text(get("Name"))

    owner_name, department = clean_text(get("Owner")), clean_text(get("Department"))
    owner_id = lookups.owners.get((owner_name, department or "")) or lookups.owners_by_name.get(owner_name)
    if owner_id is None and owner_name:
        unmatched["owner"] += 1

    solution_type_name = match_catalog_name(
        get("Solution Type"), canonical_names_by_match_key=lookups.solution_type_index,
        initiative_name=name, field_label="Solution Type",
    )
    if solution_type_name is None and clean_text(get("Solution Type")):
        unmatched["solution_type"] += 1
    value_type_name = match_catalog_name(
        get("Flagship"), canonical_names_by_match_key=lookups.value_type_index,
        initiative_name=name, field_label="Flagship",
    )
    if value_type_name is None and clean_text(get("Flagship")):
        unmatched["value_type"] += 1

    stage = normalize_stage(get("Status"), initiative_name=name)
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

    return dict(
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
        owner_id=owner_id,
        solution_type_id=lookups.solution_types[solution_type_name] if solution_type_name else None,
        value_type_id=lookups.value_types[value_type_name] if value_type_name else None,
        risk_classification_id=risk.level,
    )
