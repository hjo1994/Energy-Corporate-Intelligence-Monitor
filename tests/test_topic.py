"""Topic classifier (transforms/topic.py): rules, order, default (pytest tests/)."""
import pytest

from ai_cockpit_ingestion.transforms.topic import DEFAULT, LABELS, RULES, classify


@pytest.mark.parametrize(("name", "description", "topic"), [
    ("EGAF CLI", "AI writes the CLI command based on natural language input", "code"),
    ("LLM API", "Make an LLM API available to developers", "code"),
    ("Individual Load and Generation Forecaster", "Clustering time series", "forecast"),
    ("Green Grid Compass", "Calculate the CO₂ intensity for bidding zones", "forecast"),
    ("Drone pictures", "Detect damage on overhead lines", "monitor"),
    ("BIM models", "Link the models to the GIS", "engdata"),
    ("Tender texts", "Proofread the documents", "docreview"),
    ("Objection handling", "Draft the letters to the citizens", "writing"),
    ("Scotty", "General chatbot for the employees", "knowledge"),
    ("Invoices", "Match supplier invoices", "procure"),
    ("Power Apps flow", "Route the incoming tickets", "automation"),
])
def test_each_rule(name, description, topic):
    assert classify(name, description) == topic


def test_first_match_wins_and_case_is_ignored():
    # "forecast" (2nd rule) and "chatbot" (knowledge) both match: the earlier rule wins
    assert classify("PRICE FORECAST CHATBOT", None) == "forecast"
    # "\bcode" needs a word start: "barcode" is not code
    assert classify("Barcode labels", None) == DEFAULT


def test_default_and_missing_text():
    assert classify("Data Science CookBook", "A collection of best practices") == DEFAULT
    assert classify(None, None) == DEFAULT


def test_every_topic_has_a_label():
    assert set(LABELS) == {key for key, _ in RULES} | {DEFAULT}
