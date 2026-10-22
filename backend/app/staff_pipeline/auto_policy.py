"""Политика приёма банка, отдельная от рекомендательного балла скоринга."""

POLICY_VERSION = "AP-2026.10.1"
POLICY_KEY = "LOW_RATING_AND_HIGH_DEBT_LOAD"
REJECT_REASON = "LOW_RATING"
DECISION_AUTHOR = "Правило банка AUTO_REJECT"


def matches(evaluation: dict) -> bool:
    facts = evaluation["facts"]
    score = facts.get("bureau_score")
    load = facts.get("debt_load_pct")
    return (not evaluation["data_incomplete"]
            and score is not None and 0 <= score < 300
            and load is not None and load > 100)
