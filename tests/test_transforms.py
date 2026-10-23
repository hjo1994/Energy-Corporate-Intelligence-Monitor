"""Unit tests for the pure transforms and the source/model wiring (no Airflow
or source workbook needed): pytest tests/
"""
from ai_cockpit_ingestion.models import EXTRACT_TABLES, LOAD_COLUMNS
from ai_cockpit_ingestion.sources import SOURCES
from ai_cockpit_ingestion.transforms.normalize import clean_text
from ai_cockpit_ingestion.transforms.risk_heuristic import RISK_LEVELS, estimate_risk_level
from ai_cockpit_ingestion.transforms.value_heuristic import estimate_value


def test_extract_tables_mirror_sheet_columns_plus_load_columns():
    for source in SOURCES:
        columns = [c.name for c in EXTRACT_TABLES[source.extract_table].columns]
        assert columns == [*source.columns, *LOAD_COLUMNS]


def test_clean_text_collapses_nbsp_and_empties():
    assert clean_text("  LLM-Based\xa0Assistant ") == "LLM-Based Assistant"
    assert clean_text("   ") is None
    assert clean_text(None) is None


def _estimate(**overrides):
    fields = dict(
        status="Idea", value=None, ai_layer=None, solution_type=None, flagship=None,
        solution_feasibility=None, complexity=None, cost_assessment=None,
        description=None, expected_outcome=None, added_value=None,
    )
    fields.update(overrides)
    return estimate_value(**fields)


def test_value_buckets_follow_their_own_formulas():
    # 50Hertz row "BIM Plattform 50Hz: Tunnelbau (EG)" in value_estimates_heuristic.csv
    e = _estimate(
        value="L", ai_layer="Operational and advanced AI", solution_type="BIM model for tunnel construction",
        flagship="CAPEX delivery", solution_feasibility="L", description="quality check of the model",
    )
    assert e.efficiency_eur == 8_000 * 0.5 * 60  # volume x hours saved (ml) x rate
    assert e.hypothesized_eur == e.efficiency_eur + e.quality_eur + e.risk_reduction_eur + e.strategic_eur
    assert (e.confidence_level, e.delivery_level) == ("Low", "Low")
    assert e.one_time_costs == 500_000  # from feasibility size L


def test_value_without_score_falls_back_to_ai_layer_reach():
    e = _estimate(ai_layer="AI for business process automation", solution_type="Custom agent")
    assert e.efficiency_eur == 3_000 * 1.0 * 60  # reach M, genai_process
    assert e.quality_eur > 0  # automation layer -> quality bucket applies


def test_production_means_high_delivery():
    assert _estimate(status="Production", solution_feasibility="XL").delivery_level == "High"


def test_risk_rule_chain():
    assert estimate_risk_level(name="Smart Recruiting", description="screen applicants").level == 4
    assert estimate_risk_level(name="foreman sheduling", description=None).level == 4
    assert estimate_risk_level(name="MS Copilot for M365", description=None).level == 3
    assert estimate_risk_level(name="HR chatbot", description="chatbot on HR procedures").level == 2
    assert estimate_risk_level(name="MCCS Wind Upscaling", description="upscaling of wind feed-in per substation").level == 1
    assert estimate_risk_level(name="Something", description="").level == 2


def test_risk_level_5_is_seeded_but_never_estimated():
    assert [level["id"] for level in RISK_LEVELS] == [1, 2, 3, 4, 5]
