"""Тикет 03: движок правил скоринга — разбор по правилам, версия набора, снимки оценки.

Границы срабатывания проверяются на чистой функции расчёта: она работает со словарём
фактов, поэтому каждую полосу каждого правила можно проверить ровно на её границе.
Остальное — через ручки: что видит сотрудник, что зафиксировано снимком и что клиенту
не достаётся ни в каком виде.
"""

import json
import pathlib

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Application
from app.staff_pipeline import scoring
from app.staff_pipeline.enums import PipelineEventType, SnapshotReason
from app.staff_pipeline.models import ApplicationPipeline, PipelineEvent, ScoreSnapshot, ScoreSnapshotIsImmutable
from app.staff_pipeline.scoring import Band, Rule
from tests.conftest import PROFILE, Api, company_id, submitted

BACKEND = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = BACKEND.parents[0] / "docs" / "api-examples"


@pytest.fixture
def verifier(client):
    return Api(client, "verifier")


@pytest.fixture
def underwriter(client):
    return Api(client, "underwriter")


def known(**overrides) -> dict:
    """Полный набор фактов со значениями «всё в порядке»; меняется только нужное."""
    facts = {
        "amount": 1_000_000,
        "term_months": 12,
        "rate": 18.0,
        "monthly_payment": 91_680,
        "borrowing_mode": "NEW_CREDIT",
        "amount_rub": "1 000 000 ₽",
        "bureau_score": 820,
        "rating_label": "высокий",
        "monthly_revenue": 1_800_000,
        "monthly_debt_payments": 120_000,
        "debt_load_pct": 11.8,
        "debt_load_pct_text": "12",
        "months_operating": 36,
        "required_months": 6,
        "months_operating_deficit": -30,
        "profile_missing_count": 0,
        "profile_missing_labels": "",
        "amount_to_revenue": 0.56,
    }
    facts.update(overrides)
    return facts


def rule_of(evaluation: dict, key: str) -> dict:
    return next(r for r in evaluation["rules"] if r["key"] == key)


def scoring_card(api: Api, app_id: int) -> dict:
    r = api.get(f"/staff/applications/{app_id}/scoring")
    assert r.status_code == 200, r.text
    return r.json()


def preview(api: Api, app_id: int, **body) -> dict:
    r = api.post(f"/staff/applications/{app_id}/scoring/preview", body)
    assert r.status_code == 200, r.text
    return r.json()


def short_history(api: Api, company: str = "Вектор") -> dict:
    """Заявка от бизнеса, работающего слишком мало для запрошенной суммы."""
    return submitted(api, company_id(api, company), amount=1_500_000,
                     business_profile={**PROFILE, "months_operating": 9})


def at_underwriting(verifier: Api, app_id: int) -> None:
    assert verifier.post(f"/staff/applications/{app_id}/claim").status_code == 200
    assert verifier.post(f"/staff/applications/{app_id}/pass-to-underwriting",
                         {"comment": "Анкета полная"}).status_code == 200


def decided(verifier: Api, underwriter: Api, app_id: int) -> None:
    at_underwriting(verifier, app_id)
    assert underwriter.post(f"/staff/applications/{app_id}/claim").status_code == 200
    assert underwriter.post(f"/staff/applications/{app_id}/approve", {"comment": "Одобряю"}).status_code == 200


# ---------- границы правил ----------

@pytest.mark.parametrize("score,contribution,fired", [
    (None, 0, False), (1000, 30, True), (750, 30, True), (749, 18, True), (650, 18, True),
    (649, 4, True), (500, 4, True), (499, -25, False), (300, -25, False), (299, -45, False),
    (0, -45, False),
])
def test_bureau_score_rule_boundaries(score, contribution, fired):
    label = {None: None}.get(score, "любой")
    rule = rule_of(scoring.apply_rules(known(bureau_score=score, rating_label=label)), "BUREAU_SCORE")
    assert (rule["contribution"], rule["fired"]) == (contribution, fired)


@pytest.mark.parametrize("load,contribution,fired", [
    (None, 0, False), (0, 12, True), (49.9, 12, True), (50, 0, True), (80, 0, True),
    (80.1, -30, False), (100, -30, False), (100.1, -45, False),
])
def test_debt_load_rule_boundaries(load, contribution, fired):
    rule = rule_of(scoring.apply_rules(known(debt_load_pct=load, debt_load_pct_text=str(load))), "DEBT_LOAD")
    assert (rule["contribution"], rule["fired"]) == (contribution, fired)


@pytest.mark.parametrize("deficit,contribution,fired", [
    (None, 0, False), (-1, 10, True), (0, 10, True), (1, -20, False), (18, -20, False),
])
def test_months_operating_rule_boundaries(deficit, contribution, fired):
    rule = rule_of(scoring.apply_rules(known(months_operating_deficit=deficit)), "MONTHS_OPERATING")
    assert (rule["contribution"], rule["fired"]) == (contribution, fired)
    # Правило не ругается молча: у несработавшего есть готовая причина отказа из справочника.
    expected_reason = None if fired else ("INSUFFICIENT_DATA" if deficit is None else "SHORT_HISTORY")
    assert rule["suggested_reject_reason_code"] == expected_reason


@pytest.mark.parametrize("missing,contribution,fired", [
    (0, 10, True), (1, -10, False), (2, -10, False), (3, -20, False), (5, -20, False),
])
def test_profile_completeness_rule_boundaries(missing, contribution, fired):
    rule = rule_of(scoring.apply_rules(known(profile_missing_count=missing)), "PROFILE_COMPLETENESS")
    assert (rule["contribution"], rule["fired"]) == (contribution, fired)


@pytest.mark.parametrize("ratio,contribution,fired", [
    (None, 0, False), (0.1, 8, True), (1, 8, True), (1.01, 0, True), (3, 0, True),
    (3.01, -15, False), (6, -15, False), (6.01, -30, False),
])
def test_amount_to_revenue_rule_boundaries(ratio, contribution, fired):
    rule = rule_of(scoring.apply_rules(known(amount_to_revenue=ratio)), "AMOUNT_TO_REVENUE")
    assert (rule["contribution"], rule["fired"]) == (contribution, fired)


@pytest.mark.parametrize("amount,months", [
    (100_000, 6), (1_000_000, 6), (1_000_001, 12), (3_000_000, 12), (3_000_001, 24), (10_000_000, 24),
])
def test_required_months_by_amount_boundaries(amount, months):
    assert scoring.required_months(amount) == months


@pytest.mark.parametrize("fact,expected", [
    ({}, "APPROVE"),                                                # 100 баллов
    ({"bureau_score": 649, "rating_label": "средний"}, "MANUAL"),   # 74 балла
    ({"bureau_score": 300, "rating_label": "низкий"}, "MANUAL"),    # 45 баллов
    ({"bureau_score": 299, "rating_label": "низкий"}, "REJECT"),    # 25 баллов
    ({"bureau_score": 820, "rating_label": "высокий",
      "months_operating_deficit": 3, "profile_missing_count": 1}, "MANUAL"),  # 70 баллов
])
def test_recommendation_follows_the_score_bands(fact, expected):
    assert scoring.apply_rules(known(**fact))["recommendation"] == expected


def test_score_never_leaves_the_declared_range():
    worst = scoring.apply_rules(known(bureau_score=0, rating_label="низкий", debt_load_pct=200,
                                      debt_load_pct_text="200", months_operating_deficit=10,
                                      profile_missing_count=5, amount_to_revenue=12))
    best = scoring.apply_rules(known())
    assert (worst["total_score"], best["total_score"]) == (scoring.SCORE_MIN, scoring.SCORE_MAX)
    assert worst["recommendation"] == "REJECT"


def test_missing_data_sends_the_decision_to_a_human_even_with_a_high_score():
    """Без рейтинга бюро и без выручки автоматика вывод не делает — так было и раньше."""
    evaluation = scoring.apply_rules(known(bureau_score=None, rating_label=None))
    assert evaluation["data_incomplete"] is True
    assert evaluation["recommendation"] == "MANUAL"
    assert rule_of(evaluation, "BUREAU_SCORE")["details"] == "Рейтинг бюро недоступен — оценка собрана без него"


def test_a_new_rule_needs_no_change_in_the_calculation():
    """Правила описаны данными: набор расширяется таблицей, а не правкой расчёта."""
    extra = Rule(
        key="REVENUE_FLOOR",
        title="Минимальная выручка",
        fact="monthly_revenue",
        bands=(
            Band(">=", 1_000_000, 5, True, "Выручка {monthly_revenue} — выше порога"),
            Band("any", None, -5, False, "Выручка {monthly_revenue} — ниже порога"),
        ),
    )
    base = scoring.apply_rules(known(bureau_score=649, rating_label="средний"))
    extended = scoring.apply_rules(known(bureau_score=649, rating_label="средний"),
                                   ruleset=(*scoring.RULESET, extra))
    assert len(extended["rules"]) == len(base["rules"]) + 1
    assert rule_of(extended, "REVENUE_FLOOR")["contribution"] == 5
    assert extended["total_score"] == base["total_score"] + 5


# ---------- оценка в карточке сотрудника ----------

def test_scoring_card_explains_every_rule_and_names_the_ruleset_version(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    card = scoring_card(verifier, app["id"])

    assert card["ruleset_version"] == scoring.RULESET_VERSION
    assert [r["key"] for r in card["rules"]] == [
        "BUREAU_SCORE", "DEBT_LOAD", "MONTHS_OPERATING", "PROFILE_COMPLETENESS", "AMOUNT_TO_REVENUE"]
    assert card["total_score"] == 100 and card["recommendation"] == "APPROVE"
    assert card["recommendation_label"] == "Одобрить"
    for rule in card["rules"]:
        assert rule["title"] and rule["details"], rule["key"]
        assert isinstance(rule["fired"], bool) and isinstance(rule["contribution"], int)
    # итог складывается ровно из разбора — проверить сумму может и сотрудник, и жюри
    assert card["total_score"] == card["base_score"] + sum(r["contribution"] for r in card["rules"])
    assert card["facts"]["bureau_score"] == 820


def test_both_department_roles_see_the_same_scoring(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "Маяк"))
    assert scoring_card(verifier, app["id"])["total_score"] == scoring_card(underwriter, app["id"])["total_score"]
    assert scoring_card(verifier, app["id"])["recommendation"] == "MANUAL"


def test_legacy_scoring_block_of_the_staff_card_did_not_change(alexey, verifier):
    """Прежний блок оценки в существующей карточке — те же поля и тот же смысл."""
    app = submitted(alexey, company_id(alexey, "ИП"))
    block = verifier.get(f"/staff/applications/{app['id']}").json()["scoring"]
    recorded = json.loads((EXAMPLES / "staff_card.json").read_text(encoding="utf-8"))["scoring"]

    assert set(block) == set(recorded)
    assert block["bureau_score"] == 820
    assert block["recommendation"] == "APPROVE" and block["recommendation_label"] == "Одобрить"
    assert block["reasons"] == ["Высокий рейтинг и комфортная долговая нагрузка"]
    # ни баллов, ни правил, ни версии набора в прежнем блоке не появилось
    assert not {"total_score", "rules", "ruleset_version"} & set(block)


def test_short_working_history_lowers_the_score_and_suggests_a_ready_reason(alexey, verifier):
    app = short_history(alexey)
    card = scoring_card(verifier, app["id"])
    rule = rule_of(card, "MONTHS_OPERATING")

    assert rule["fired"] is False and rule["contribution"] == -20
    assert "9 мес." in rule["details"] and "12 мес." in rule["details"]
    assert rule["suggested_reject_reason_code"] == "SHORT_HISTORY"
    reasons = {r["code"]: r["text"] for r in verifier.get("/staff/reject-reasons").json()["items"]}
    assert rule["suggested_reject_reason_text"] == reasons["SHORT_HISTORY"]
    assert card["recommendation"] == "REJECT"


# ---------- снимки оценки ----------

def snapshot_rows(app_id: int) -> list[ScoreSnapshot]:
    with SessionLocal() as db:
        return list(db.scalars(select(ScoreSnapshot).where(
            ScoreSnapshot.application_id == app_id).order_by(ScoreSnapshot.id)))


def test_snapshot_is_taken_on_intake_and_on_decision(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    assert snapshot_rows(app["id"]) == [], "до появления у сотрудника оценка не фиксируется"

    verifier.get("/staff/queue")  # приём в конвейер
    intake = snapshot_rows(app["id"])
    assert [s.reason for s in intake] == [SnapshotReason.ON_INTAKE]
    assert intake[0].total_score == 100 and intake[0].ruleset_version == scoring.RULESET_VERSION
    assert intake[0].breakdown["rules"][0]["key"] == "BUREAU_SCORE"

    decided(verifier, underwriter, app["id"])
    assert [s.reason for s in snapshot_rows(app["id"])] == [
        SnapshotReason.ON_INTAKE, SnapshotReason.ON_DECISION]

    card = scoring_card(underwriter, app["id"])
    assert card["is_snapshot"] is True and card["snapshot_reason"] == SnapshotReason.ON_DECISION
    assert [s["reason"] for s in card["snapshots"]] == [SnapshotReason.ON_INTAKE, SnapshotReason.ON_DECISION]


def test_decision_history_record_carries_the_snapshot(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    decided(verifier, underwriter, app["id"])
    history = verifier.get(f"/staff/applications/{app['id']}/pipeline").json()["history"]
    decision = next(e for e in history if e["type"] == PipelineEventType.DECISION_MADE)

    snapshot = snapshot_rows(app["id"])[-1]
    assert decision["payload"]["score_snapshot_id"] == snapshot.id
    assert decision["payload"]["ruleset_version"] == scoring.RULESET_VERSION
    assert decision["payload"]["total_score"] == snapshot.total_score


def test_intake_snapshot_is_not_duplicated_by_repeated_openings(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    for _ in range(3):
        verifier.get("/staff/queue")
        scoring_card(verifier, app["id"])
        verifier.get(f"/staff/applications/{app['id']}/pipeline")
    assert len(snapshot_rows(app["id"])) == 1


def test_a_new_ruleset_version_does_not_change_an_already_decided_application(
        alexey, verifier, underwriter, monkeypatch):
    """Ключевое свойство: правка правил не переписывает обоснование вчерашних решений."""
    old = submitted(alexey, company_id(alexey, "ИП"))
    decided(verifier, underwriter, old["id"])
    before = scoring_card(underwriter, old["id"])
    assert before["is_snapshot"] is True

    # подменяем набор правил: тот же факт, другие баллы, другая версия
    harsher = Rule(key="BUREAU_SCORE", title="Рейтинг кредитного бюро", fact="bureau_score",
                   bands=(Band("any", None, -45, False, "Новая редакция правил"),))
    monkeypatch.setattr(scoring, "RULESET", (harsher, *scoring.RULESET[1:]))
    monkeypatch.setattr(scoring, "RULESET_VERSION", "RS-2026.10.2")

    after = scoring_card(underwriter, old["id"])
    assert after["ruleset_version"] == before["ruleset_version"] == "RS-2026.10.1"
    assert after["total_score"] == before["total_score"]
    assert after["rules"] == before["rules"]
    assert after["recommendation"] == before["recommendation"]

    # а заявка, по которой решение ещё не принято, считается по новой версии
    fresh = submitted(alexey, company_id(alexey, "Маяк"))
    live = scoring_card(underwriter, fresh["id"])
    assert live["is_snapshot"] is False and live["ruleset_version"] == "RS-2026.10.2"
    assert rule_of(live, "BUREAU_SCORE")["contribution"] == -45


def test_snapshots_cannot_be_rewritten_or_deleted(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    verifier.get("/staff/queue")
    with SessionLocal() as db:
        snapshot = db.scalars(select(ScoreSnapshot).where(
            ScoreSnapshot.application_id == app["id"])).first()
        snapshot.total_score = 1
        with pytest.raises(ScoreSnapshotIsImmutable):
            db.commit()
        db.rollback()
    with SessionLocal() as db:
        snapshot = db.scalars(select(ScoreSnapshot).where(
            ScoreSnapshot.application_id == app["id"])).first()
        db.delete(snapshot)
        with pytest.raises(ScoreSnapshotIsImmutable):
            db.commit()
        db.rollback()
    assert snapshot_rows(app["id"])[0].total_score == 100


# ---------- предварительный пересчёт ----------

def test_preview_shows_which_rules_change_on_other_terms(alexey, underwriter):
    app = short_history(alexey)
    result = preview(underwriter, app["id"], amount=1_000_000)

    assert result["requested"]["amount"] == 1_500_000
    assert result["requested"]["recommendation"] == "REJECT"
    assert result["preview"]["amount"] == 1_000_000
    assert result["preview"]["total_score"] > result["requested"]["total_score"]
    assert result["preview"]["recommendation"] == "MANUAL"
    changed = {r["key"]: r for r in result["changed_rules"]}
    assert changed["MONTHS_OPERATING"]["before"] == -20
    assert changed["MONTHS_OPERATING"]["after"] == 10
    assert result["preview"]["monthly_payment"] < result["requested"]["monthly_payment"]
    assert result["note"] == "Предварительный расчёт. Сохранённая заявка не меняется."


def test_preview_leaves_the_stored_application_untouched(alexey, underwriter):
    app = short_history(alexey)
    scoring_card(underwriter, app["id"])  # приём в конвейер и снимок при приёме — до пересчёта
    with SessionLocal() as db:
        row = db.get(Application, app["id"])
        before = (row.amount, row.term_months, row.preliminary_rate, row.preliminary_payment, row.status)
    snapshots_before = len(snapshot_rows(app["id"]))

    preview(underwriter, app["id"], amount=1_000_000, term_months=36)

    with SessionLocal() as db:
        row = db.get(Application, app["id"])
        assert (row.amount, row.term_months, row.preliminary_rate, row.preliminary_payment,
                row.status) == before
    assert len(snapshot_rows(app["id"])) == snapshots_before, "пересчёт снимков не делает"
    assert alexey.get(f"/applications/{app['id']}").json()["amount"] == 1_500_000


def test_preview_without_fields_returns_the_current_evaluation(alexey, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    result = preview(underwriter, app["id"])
    assert result["changed_rules"] == []
    assert result["preview"] == result["requested"]


@pytest.mark.parametrize("body,field", [
    ({"amount": 10_000}, "amount"),
    ({"amount": 99_000_000}, "amount"),
    ({"amount": 1_010_000}, "amount"),
    ({"term_months": 100}, "term_months"),
])
def test_preview_checks_the_same_limits_as_other_terms(alexey, underwriter, body, field):
    app = submitted(alexey, company_id(alexey, "ИП"))
    r = underwriter.post(f"/staff/applications/{app['id']}/scoring/preview", body)
    assert r.status_code == 422, r.text
    assert field in r.json()["error"]["fields"]


def test_preview_of_refinance_is_limited_by_the_debt_balance(alexey, underwriter):
    ip = company_id(alexey, "ИП")
    loan = alexey.get(f"/companies/{ip}/loans").json()["items"][0]
    app = submitted(alexey, ip, mode="REFINANCE", existing_loan_id=loan["id"], term_months=24)
    balance = app["amount"]
    assert preview(underwriter, app["id"], amount=balance - 100_000)["preview"]["amount"] == balance - 100_000
    r = underwriter.post(f"/staff/applications/{app['id']}/scoring/preview",
                         {"amount": balance + 100_000})
    assert r.status_code == 422 and "amount" in r.json()["error"]["fields"]


# ---------- рекомендация, решение и клиент ----------

def test_recommendation_stays_a_recommendation_and_does_not_decide(alexey, verifier, underwriter):
    """Отрицательная рекомендация не запрещает одобрить: решение принимает человек."""
    app = short_history(alexey)
    assert scoring_card(underwriter, app["id"])["recommendation"] == "REJECT"
    decided(verifier, underwriter, app["id"])

    assert alexey.get(f"/applications/{app['id']}").json()["status"] == "APPROVED"
    snapshot = snapshot_rows(app["id"])[-1]
    assert snapshot.reason == SnapshotReason.ON_DECISION
    assert snapshot.recommendation == "REJECT", "в снимке осталось, что сотрудник решил иначе"


def test_scoring_is_never_shown_to_the_client(alexey, verifier, underwriter):
    app = short_history(alexey)
    scoring_card(underwriter, app["id"])
    decided(verifier, underwriter, app["id"])

    assert alexey.get(f"/staff/applications/{app['id']}/scoring").status_code == 403
    assert alexey.post(f"/staff/applications/{app['id']}/scoring/preview", {"amount": 900_000}).status_code == 403

    client_view = alexey.get(f"/applications/{app['id']}")
    assert not {"total_score", "recommendation", "rules", "ruleset_version", "scoring",
                "snapshots"} & set(client_view.json())
    for marker in ("RS-2026.10.1", "SHORT_HISTORY", "BUREAU_SCORE", "MONTHS_OPERATING",
                   "total_score", "Рейтинг 420"):
        assert marker not in client_view.text, marker


def test_existing_staff_account_also_gets_snapshots(alexey, staff):
    """Прежняя учётная запись работает как раньше, но оценка по её решениям фиксируется."""
    app = submitted(alexey, company_id(alexey, "ИП"))
    assert staff.post(f"/staff/applications/{app['id']}/approve", {"comment": "Как раньше"}).status_code == 200
    assert [s.reason for s in snapshot_rows(app["id"])] == [
        SnapshotReason.ON_INTAKE, SnapshotReason.ON_DECISION]
    assert scoring_card(staff, app["id"])["is_snapshot"] is True


def test_failed_decision_leaves_no_snapshot(alexey, verifier, underwriter):
    """Снимок живёт в одной транзакции с решением: не прошло решение — нет и снимка."""
    app = submitted(alexey, company_id(alexey, "ИП"))
    at_underwriting(verifier, app["id"])
    underwriter.post(f"/staff/applications/{app['id']}/claim")
    r = underwriter.post(f"/staff/applications/{app['id']}/counter-offer",
                         {"amount": 800_000, "term_months": 18, "rate": 19.5, "comment": "   "})
    assert r.status_code == 422, r.text
    assert [s.reason for s in snapshot_rows(app["id"])] == [SnapshotReason.ON_INTAKE]


@pytest.mark.parametrize("body,status", [({"amount": 900_000}, 200), ({"amount": 1}, 422)])
def test_preview_before_intake_does_not_write_anything(alexey, underwriter, body, status):
    app = submitted(alexey, company_id(alexey, "ИП"))
    before = alexey.get(f"/applications/{app['id']}").json()
    response = underwriter.post(f"/staff/applications/{app['id']}/scoring/preview", body)
    assert response.status_code == status, response.text
    assert snapshot_rows(app["id"]) == []
    with SessionLocal() as db:
        assert db.get(ApplicationPipeline, app["id"]) is None
        assert db.scalars(select(PipelineEvent).where(PipelineEvent.application_id == app["id"])).all() == []
    assert alexey.get(f"/applications/{app['id']}").json() == before


@pytest.mark.parametrize("revenue,points", [(1_000_000, 8), (999_999, 0),
                                           (333_334, 0), (333_333, -15),
                                           (166_667, -15), (166_666, -30)])
def test_revenue_ratio_is_not_rounded_before_rule_evaluation(alexey, verifier, revenue, points):
    app = submitted(alexey, company_id(alexey, "ИП"), amount=1_000_000,
                    business_profile={**PROFILE, "monthly_revenue": revenue})
    assert rule_of(scoring_card(verifier, app["id"]), "AMOUNT_TO_REVENUE")["contribution"] == points


@pytest.mark.parametrize("total_payment,points", [(499_999, 12), (500_000, 0),
                                                 (800_000, 0), (800_001, -30),
                                                 (1_000_000, -30), (1_000_001, -45)])
def test_debt_load_is_not_rounded_before_rule_evaluation(alexey, verifier, total_payment, points):
    app = submitted(alexey, company_id(alexey, "ИП"), amount=1_000_000)
    with SessionLocal() as db:
        row = db.get(Application, app["id"])
        row.business_profile = {**PROFILE, "monthly_revenue": 1_000_000,
                                "monthly_debt_payments": total_payment - row.preliminary_payment}
        db.commit()
    assert rule_of(scoring_card(verifier, app["id"]), "DEBT_LOAD")["contribution"] == points


@pytest.mark.parametrize("action,body", [
    ("approve", {"comment": "Подтверждаю"}),
    ("reject", {"reason_code": "LOW_RATING"}),
    ("counter-offer", {"amount": 500_000, "term_months": 24, "rate": 18, "comment": "Уменьшить сумму"}),
])
def test_all_decisions_freeze_the_evaluation(alexey, staff, monkeypatch, action, body):
    app = submitted(alexey, company_id(alexey, "ИП"))
    response = staff.post(f"/staff/applications/{app['id']}/{action}", body)
    assert response.status_code == 200, response.text
    before = scoring_card(staff, app["id"])
    assert before["snapshot_reason"] == "ON_DECISION"
    monkeypatch.setattr(scoring, "RULESET", ())
    monkeypatch.setattr(scoring, "RULESET_VERSION", "RS-2026.10.2")
    monkeypatch.setattr(scoring, "RECOMMENDATION_LABELS", {"APPROVE": "Другая подпись"})
    assert scoring_card(staff, app["id"]) == before


def test_supplement_and_new_decision_keep_both_snapshots(alexey, staff, monkeypatch):
    app = short_history(alexey)
    response = staff.post(f"/staff/applications/{app['id']}/counter-offer",
                          {"amount": 500_000, "term_months": 24, "rate": 18, "comment": "Уменьшить сумму"})
    assert response.status_code == 200, response.text
    original = snapshot_rows(app["id"])[-1].breakdown
    monkeypatch.setattr(scoring, "RULESET_VERSION", "RS-2026.10.2")
    response = alexey.post(f"/applications/{app['id']}/supplement",
                           {"answer_text": "Уточнение", "fields": {"months_operating": 36}})
    assert response.status_code == 200, response.text
    live = scoring_card(staff, app["id"])
    assert live["is_snapshot"] is False and live["ruleset_version"] == "RS-2026.10.2"
    assert rule_of(live, "MONTHS_OPERATING")["contribution"] == 10
    assert staff.post(f"/staff/applications/{app['id']}/approve", {"comment": "Одобряю"}).status_code == 200
    rows = snapshot_rows(app["id"])
    assert [s.reason for s in rows] == ["ON_INTAKE", "ON_DECISION", "ON_DECISION"]
    assert rows[1].breakdown == original
    assert rows[2].ruleset_version == "RS-2026.10.2"
    assert scoring_card(staff, app["id"])["facts"]["months_operating"] == 36
