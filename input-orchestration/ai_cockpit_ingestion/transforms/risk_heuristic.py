"""Risk classification of an initiative per the Rahmenbetriebsvereinbarung KI
(50Hertz/GBR, 01.03.2026) — an ESTIMATE from free text, not an assessment.

The agreement grades AI systems solely by their impact on employees'
workplaces (Abb. 2): personal data of employees, automated decisions about
employees, profiling, performance/behaviour monitoring. None of that is a
structured field in the source workbook, so the level is derived by a rule
chain over Name/Description/Expected Outcome/Added Value, Department,
Flagship and Solution Type; first matching rule wins:

1. automated decisions or profiling about employees/applicants -> level 4
2. employee personal data, performance/behaviour evaluation, agents with
   access to personal data -> level 3
3. explicit employee tools (assistants, chatbots, ticket routing) -> level 2
4. no employee relation (forecasting/optimisation on grid, market or asset
   data, pure platforms) -> level 1
5. everything else: a tool for employees without decisions about people -> level 2
Level 5 is never estimated; it is only assigned after an explicit review.

Same rule chain as risiko/risk_classification_estimates.csv (Thread
"Nutzen-Quantifizierung"), turned into keyword rules so it runs unattended.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Seed for the RiskClassification config table (Abb. 1-3 of the agreement).
# derived_action lists the follow-up activities, cumulative per level.
RISK_LEVELS: tuple[dict, ...] = (
    {
        "id": 1,
        "name": "Sehr geringes Risiko",
        "description": "Keine oder vernachlässigbare Auswirkungen auf Beschäftigte. Keine "
        "personenbezogenen Daten, keine Automatisierung. Beispiele: digitales Whiteboard, "
        "Raumbelegungssystem.",
        "derived_action": "Information des Betriebsrats; Dokumentation im Technikregister "
        "(KI-Register); Eintrag in die Übersichtsliste/Kurzinfo.",
    },
    {
        "id": 2,
        "name": "Geringes Risiko",
        "description": "Geringe Auswirkungen möglich, z. B. durch einfache Datenverarbeitung oder "
        "Automatisierung. Keine Entscheidungsrelevanz. Beispiele: Zeiterfassungssystem ohne "
        "Auswertung, E-Mail-Filter.",
        "derived_action": "Wie Stufe 1, zusätzlich: frühzeitige Information des Betriebsrats; "
        "vereinfachte Gefährdungsbeurteilung; Schulungsangebot; KI-Steckbrief; Monitoring.",
    },
    {
        "id": 3,
        "name": "Mittleres Risiko",
        "description": "Mögliche Auswirkungen auf Arbeitsabläufe, Leistungskontrolle oder "
        "personenbezogene Daten. Keine vollautomatisierten Entscheidungen. Beispiele: Microsoft "
        "Viva Insights, CRM-Systeme mit Reporting, Videoüberwachung ohne KI, Schichtplanung mit "
        "KI (z. B. Kronos), KI-Agenten mit mittlerem Risiko.",
        "derived_action": "Wie Stufe 2, zusätzlich: Gefährdungsbeurteilung; "
        "Menschenrechtsfolgeabschätzung; Auswirkungsfolgenabschätzung; Testbetrieb mit "
        "Evaluation; Beteiligung des Betriebsrats; bei Bedarf Abschluss oder Anpassung "
        "betrieblicher Regelungen (Betriebsvereinbarung evtl.); Modelltests; "
        "Grundrechtsfolgenabschätzung vorab an den GBR.",
    },
    {
        "id": 4,
        "name": "Hohes Risiko",
        "description": "Automatisierte Entscheidungen mit Einfluss auf Beschäftigte. "
        "KI-Komponenten mit Lernfähigkeit oder Profilbildung. Beispiele: Bewerbermanagement mit "
        "KI (z. B. HireVue), Schichtplanung mit KI mit automatisierter Planerstellung durch "
        "Entscheidungen ohne Beschäftigte, Kameraüberwachung mit Gesichtserkennung, KI-Agenten "
        "mit hohem Risiko.",
        "derived_action": "Wie Stufe 3, zusätzlich: vollständige Risikoanalyse inkl. "
        "EU-KI-Klassifizierung; Testbetrieb unter Aufsicht; Zustimmung des Betriebsrats; "
        "Abschluss oder Anpassung betrieblicher Regelungen (Betriebsvereinbarung ja).",
    },
    {
        "id": 5,
        "name": "Sehr hohes (nicht vertretbares) Risiko",
        "description": "Systeme mit nicht kontrollierbaren Auswirkungen, "
        "Diskriminierungspotenzial, Intransparenz oder Verstoß gegen Grundrechte. Beispiele: "
        "Emotionserkennung am Arbeitsplatz, KI-basierte Lügendetektoren, Systeme ohne "
        "Nachvollziehbarkeit oder Widerspruchsmöglichkeit, KI-Agenten mit sehr hohem Risiko.",
        "derived_action": "Verbot der Einführung; Dokumentation der Ablehnung (Eintrag in die "
        "Übersichtsliste mit Begründung); ggf. Meldung an Aufsichtsbehörden.",
    },
)

_FLAGS = re.IGNORECASE

# Rule 1 -> level 4: automated decisions or profiling about employees/applicants.
_LEVEL_4 = [
    ("recruiting/applicant screening", r"\brecruiting\b|applicant|candidates? (screening|selection|matching)|talent acquisition|bewerb"),
    (
        "workforce/shift scheduling",
        r"workforce sch?edul|shift (plan|schedul)|schedul\w* of (staff|crews?|technicians|foremen)"
        r"|fore(man|men) s\w*dul|field service management|crew (plan|schedul)|einsatzplanung|schichtplan",
    ),
    ("autonomous response on user accounts", r"orchestration, automation,? (and )?response|\bsoar\b"),
]

# Rule 2 -> level 3: employee personal data, performance/behaviour evaluation,
# agents acting on personal data.
_LEVEL_3 = [
    (
        "profiling via personalised learning",
        r"learning experience|\blxp\b|personali[sz]ed (learning|training)|training (&|and) simulation",
    ),
    ("performance evaluation", r"performance tracking|employee performance|productivity tracking|viva insights"),
    (
        "behaviour/anomaly detection on users",
        r"end-?point detection|\bedr\b|\bsiem\b|security incident and event|user behaviou?r",
    ),
    (
        "employee personal data",
        r"travel expense|expense (registration|report)|copilot for m365|m365 copilot|mailbox"
        r"|audio transcri|audio record|user/system context|user context|personal data|employee data|\bhr data|payroll",
    ),
    ("agents on enterprise data incl. personal data", r"\bjoule\b|agentic pm|autonomous agents?|access sap data"),
    ("decision support for operators", r"operator assistan"),
]

# Rule 3 -> level 1: no relation to employees.
_LEVEL_1 = [
    ("platform/infrastructure without own use case", r"platform|plattform|infrastructure|data lake|data hub"),
    (
        "forecasting/optimisation on grid, market or asset data",
        r"forecast|prognos|predict|optimi[sz]|anomal|load flow|grid (model|calculation|simulation)"
        r"|congestion|balancing|market|asset health|condition monitoring|image recognition|drone|lidar|satellite"
        r"|frequency|redispatch|outage|grid losses|losses compensation|feed-in|substation|tower|nameplate"
        r"|equipment|leakage|computer vision|imbalance|afrr|\bbrp|co2|co₂|bidding zone|cable calc"
        r"|root cause|data quality|model integrity",
    ),
]

# Checked before rule 3, so that e.g. a "knowledge platform" chatbot or
# ticket "routing optimization" is not mistaken for a technical model.
_LEVEL_2 = [
    ("assistant/chatbot for employees", r"chatbot|assistant|copilot|knowledge"),
    ("classification/routing of requests or tickets", r"ticket|routing|inbox|incoming (mail|request)"),
]


@dataclass(frozen=True)
class RiskEstimate:
    level: int
    rule: str


def estimate_risk_level(
    *,
    name: str | None,
    description: str | None,
    expected_outcome: str | None = None,
    added_value: str | None = None,
    solution_type: str | None = None,
) -> RiskEstimate:
    text = " ".join(t for t in (name, description, expected_outcome, added_value) if t)

    for label, pattern in _LEVEL_4:
        if re.search(pattern, text, _FLAGS):
            return RiskEstimate(4, label)
    for label, pattern in _LEVEL_3:
        if re.search(pattern, text, _FLAGS):
            return RiskEstimate(3, label)
    for label, pattern in _LEVEL_2:
        if re.search(pattern, text, _FLAGS):
            return RiskEstimate(2, label)
    for label, pattern in _LEVEL_1:
        if re.search(pattern, text, _FLAGS):
            return RiskEstimate(1, label)
    if solution_type and solution_type.startswith("Custom AI/ML"):
        return RiskEstimate(1, "ML model without employee relation")
    return RiskEstimate(2, "tool for employees without decisions about people")
