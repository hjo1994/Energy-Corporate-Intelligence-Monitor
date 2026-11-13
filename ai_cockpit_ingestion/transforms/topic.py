"""Topic of a use case for the exploration view (AssessedInitiatives.Topic),
derived from the silver text, deterministic:

- the text is Name + " " + Description of the current silver version;
- the rules are case-insensitive regular expressions, checked in order; the
  first match gives the topic key, no match gives DEFAULT ("other");
- gold stores the key, the display labels are LABELS (code only for now).
"""
from __future__ import annotations

import re

RULES = tuple(
    (key, re.compile(pattern, re.IGNORECASE))
    for key, pattern in (
        ("code", r"\bcode|developer|unit test|integration test|github|\bcli\b|devops|software develop|\bapi\b"
                 r"|refactor|pull request|programming"),
        ("forecast", r"forecast|predict|time series|load and generation|optimi[sz]|dimensioning|balanc|losses"
                     r"|price|redispatch|afrr|co₂|co2|upscal|imbalance|reserve"),
        ("monitor", r"monitor|anomal|detect|drone|inspection|sf6|camera|alarm|sensor|condition|\bedr\b|cyber"
                    r"|vegetation|fault|incident"),
        ("engdata", r"\bbim\b|\bgis\b|plate|image|picture|photo|calibration|simulation|cable|substation"
                    r"|asset data|circuit|drawing|technical specification|database"),
        ("docreview", r"check|review|verif|complian|consisten|quality|requirement|accessib|proofread"),
        ("writing", r"letter|e-?mail|\bmail\b|correspond|reply|replies|respons|objection|draft|notice"
                    r"|communication|answer|report|summar|transcri|minutes|meeting"),
        ("knowledge", r"chatbot|knowledge|search|question|assistant|copilot|wiki|documentation|learning|faq"),
        ("procure", r"procure|supplier|contract|tender|purchas|invoic|treasury|controlling|accounting|closing"
                    r"|expense|\bsap\b|finance|\bhr\b|job description|recruit|travel"),
        ("automation", r"automat|power apps|rpa|workflow|ticket|routing|request|scheduling"),
    )
)
DEFAULT = "other"
LABELS = {
    "code": "Code & developer tools",
    "forecast": "Forecasting & optimisation",
    "monitor": "Monitoring & detection",
    "engdata": "Engineering & asset data",
    "docreview": "Document checking",
    "writing": "Letters, replies & reports",
    "knowledge": "Knowledge & chatbots",
    "procure": "Procurement, finance & HR",
    "automation": "Process automation",
    DEFAULT: "Other topics",
}


def classify(name: str | None, description: str | None) -> str:
    """Topic key of a use case: the first rule matching its name and description."""
    text = f"{name or ''} {description or ''}"
    return next((key for key, pattern in RULES if pattern.search(text)), DEFAULT)
