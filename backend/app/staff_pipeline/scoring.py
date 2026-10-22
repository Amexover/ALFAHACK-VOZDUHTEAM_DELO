"""Движок правил скоринга: разбор по правилам, версия набора и снимки оценки.

Три свойства, которых не было у прежней рекомендации.

**Прозрачность.** Оценка складывается из правил, и по каждому видно: формулировка,
выполнено требование или нет, сколько баллов дало или отняло и чем обосновано.
Сотрудник может проверить оценку, а не поверить надписи.

**Версионированность.** У набора правил есть версия, и она приходит вместе с оценкой:
видно, по какой именно версии посчитана заявка.

**Неизменность задним числом.** Оценка фиксируется снимком при приёме заявки и ещё раз
при вынесении решения. Завтрашняя правка правил не меняет обоснование вчерашних решений —
для банка это обязательное свойство, а не удобство.

Правила описаны данными: набор `RULESET` — это таблица, а не цепочка условий.
Правило — факт плюс полосы значений; добавление нового правила не требует правки
расчёта. Сам расчёт (`apply_rules`) чистый: он работает со словарём фактов и ничего
не знает ни про базу, ни про запрос — поэтому границы срабатывания проверяются тестом
напрямую.

Рекомендация остаётся рекомендацией: решение принимает человек, клиенту оценка не
отдаётся ни в каком виде.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog, pricing
from app.enums import Status
from app.models import Application
from app.simulators import bureau
from app.staff_pipeline.enums import SnapshotReason
from app.staff_pipeline.models import ScoreSnapshot

# Версия набора правил. Меняется вместе с составом правил или баллами: по ней видно,
# по какой редакции политики банка оценена заявка.
RULESET_VERSION = "RS-2026.10.1"

# Стартовый балл: правила добавляют и отнимают от него.
BASE_SCORE = 30
SCORE_MIN = 0
SCORE_MAX = 100

# Границы рекомендации. Данные, а не ветвления: порог меняется здесь.
RECOMMENDATION_BANDS = ((80, "APPROVE"), (40, "MANUAL"), (None, "REJECT"))
RECOMMENDATION_LABELS = {
    "APPROVE": "Одобрить",
    "REJECT": "Отказать",
    "MANUAL": "На усмотрение сотрудника",
}
# Когда данных не хватает, автоматика не делает вывод ни в плюс, ни в минус.
RECOMMENDATION_WHEN_DATA_MISSING = "MANUAL"

# Статусы, при которых решение по заявке уже вынесено: оценка по ней зафиксирована.
DECIDED_STATUSES = (Status.APPROVED, Status.COUNTER_OFFER, Status.REJECTED, Status.COMPLETED)

# Сколько месяцев бизнес должен работать под запрошенную сумму: (сумма включительно, месяцев).
# Данные анкеты, которые прежний скоринг собирал и не использовал.
REQUIRED_MONTHS_BY_AMOUNT = ((1_000_000, 6), (3_000_000, 12))
REQUIRED_MONTHS_ABOVE = 24

# Операции полос. Значение `None` сравнивать нельзя — для него есть отдельная операция.
OPS = {
    ">=": lambda value, limit: value >= limit,
    ">": lambda value, limit: value > limit,
    "<=": lambda value, limit: value <= limit,
    "<": lambda value, limit: value < limit,
    "==": lambda value, limit: value == limit,
    "is_none": lambda value, _: value is None,
    "any": lambda value, _: True,
}


@dataclass(frozen=True)
class Band:
    """Полоса значений факта: условие, вклад в балл и обоснование для человека.

    `ok` — требование правила выполнено. Именно это значение уходит в ответ как `fired`:
    правило либо подтверждает заявку (вклад неотрицательный), либо работает против неё.
    `blocks_decision` — данных нет, автоматика не вправе делать вывод: рекомендация
    становится «на усмотрение сотрудника».
    """

    op: str
    limit: float | None
    points: int
    ok: bool
    details: str
    suggested_reject_reason_code: str | None = None
    blocks_decision: bool = False


@dataclass(frozen=True)
class Rule:
    """Правило: один факт и полосы его значений. Первая подошедшая полоса и применяется."""

    key: str
    title: str
    fact: str
    bands: tuple[Band, ...]


RULESET: tuple[Rule, ...] = (
    Rule(
        key="BUREAU_SCORE",
        title="Рейтинг кредитного бюро",
        fact="bureau_score",
        bands=(
            Band("is_none", None, 0, False, "Рейтинг бюро недоступен — оценка собрана без него",
                 blocks_decision=True),
            Band(">=", 750, 30, True, "Рейтинг {bureau_score} из 1000 — {rating_label}"),
            Band(">=", 650, 18, True, "Рейтинг {bureau_score} из 1000 — {rating_label}"),
            Band(">=", 500, 4, True, "Рейтинг {bureau_score} из 1000 — {rating_label}"),
            Band(">=", 300, -25, False, "Рейтинг {bureau_score} из 1000 — {rating_label}",
                 suggested_reject_reason_code="LOW_RATING"),
            Band("any", None, -45, False,
                 "Рейтинг {bureau_score} из 1000 — {rating_label}, это ниже любого порога банка",
                 suggested_reject_reason_code="LOW_RATING"),
        ),
    ),
    Rule(
        key="DEBT_LOAD",
        title="Долговая нагрузка к выручке",
        fact="debt_load_pct",
        bands=(
            Band("is_none", None, 0, False, "Нет данных о выручке — нагрузку считать не из чего",
                 suggested_reject_reason_code="INSUFFICIENT_DATA", blocks_decision=True),
            Band("<", 50, 12, True,
                 "{debt_load_pct_text} % выручки уйдёт на платежи по долгам с учётом нового платежа"),
            Band("<=", 80, 0, True,
                 "{debt_load_pct_text} % выручки уйдёт на платежи по долгам — повышенная, но допустимая нагрузка"),
            Band("<=", 100, -30, False,
                 "{debt_load_pct_text} % выручки уйдёт на платежи по долгам",
                 suggested_reject_reason_code="HIGH_DEBT_LOAD"),
            Band("any", None, -45, False,
                 "{debt_load_pct_text} % выручки — платежи по долгам превышают выручку",
                 suggested_reject_reason_code="HIGH_DEBT_LOAD"),
        ),
    ),
    Rule(
        key="MONTHS_OPERATING",
        title="Срок работы бизнеса под запрошенную сумму",
        fact="months_operating_deficit",
        bands=(
            Band("is_none", None, 0, False, "Срок работы бизнеса в анкете не указан",
                 suggested_reject_reason_code="INSUFFICIENT_DATA", blocks_decision=True),
            Band("<=", 0, 10, True,
                 "Бизнес работает {months_operating} мес. — для суммы {amount_rub} этого достаточно"),
            Band("any", None, -20, False,
                 "Бизнес работает {months_operating} мес. при запрошенных {amount_rub} — "
                 "для такой суммы нужно не меньше {required_months} мес.",
                 suggested_reject_reason_code="SHORT_HISTORY"),
        ),
    ),
    Rule(
        key="PROFILE_COMPLETENESS",
        title="Полнота анкеты",
        fact="profile_missing_count",
        bands=(
            Band("==", 0, 10, True, "Все поля анкеты заполнены"),
            Band("<=", 2, -10, False, "Не заполнено: {profile_missing_labels}",
                 suggested_reject_reason_code="INSUFFICIENT_DATA"),
            Band("any", None, -20, False, "Анкета заполнена частично, не заполнено: {profile_missing_labels}",
                 suggested_reject_reason_code="INSUFFICIENT_DATA"),
        ),
    ),
    Rule(
        key="AMOUNT_TO_REVENUE",
        title="Запрошенная сумма к выручке",
        fact="amount_to_revenue",
        bands=(
            Band("is_none", None, 0, False, "Нет данных о выручке — сумму сравнивать не с чем",
                 suggested_reject_reason_code="INSUFFICIENT_DATA", blocks_decision=True),
            Band("<=", 1, 8, True, "Сумма равна {amount_to_revenue:.2f} месячной выручки"),
            Band("<=", 3, 0, True, "Сумма равна {amount_to_revenue:.2f} месячной выручки"),
            Band("<=", 6, -15, False,
                 "Сумма равна {amount_to_revenue:.2f} месячной выручки — это много для текущего оборота",
                 suggested_reject_reason_code="HIGH_DEBT_LOAD"),
            Band("any", None, -30, False,
                 "Сумма равна {amount_to_revenue:.2f} месячной выручки — несопоставимо с оборотом",
                 suggested_reject_reason_code="HIGH_DEBT_LOAD"),
        ),
    ),
)


# ---------- факты ----------

def _num(value) -> int | float | None:
    """Число из анкеты. Анкету заполняет человек, поэтому мусор не должен ронять расчёт."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def required_months(amount: int | None) -> int | None:
    """Сколько месяцев работы банк хочет видеть под такую сумму."""
    if not amount:
        return None
    for limit, months in REQUIRED_MONTHS_BY_AMOUNT:
        if amount <= limit:
            return months
    return REQUIRED_MONTHS_ABOVE


def terms(app: Application, amount: int | None = None, term_months: int | None = None,
          score: int | None = None) -> dict:
    """Сумма, срок, ставка и платёж.

    Без аргументов — ровно те, что сохранены в заявке: оценка не должна расходиться
    с тем, что видит клиент. С аргументами — предварительный пересчёт «а если»,
    сохранённую заявку он не трогает.
    """
    use_amount = app.amount if amount is None else amount
    use_term = app.term_months if term_months is None else term_months
    if amount is None and term_months is None:
        return {
            "amount": use_amount,
            "term_months": use_term,
            "rate": float(app.preliminary_rate) if app.preliminary_rate is not None else None,
            "monthly_payment": app.preliminary_payment,
        }
    if not use_amount or not use_term:
        return {"amount": use_amount, "term_months": use_term, "rate": None, "monthly_payment": None}
    rate = pricing.preliminary_rate(score, use_term, app.borrowing_mode)
    return {
        "amount": use_amount,
        "term_months": use_term,
        "rate": float(rate),
        "monthly_payment": pricing.annuity(use_amount, rate, use_term),
    }


def facts(db: Session, app: Application, amount: int | None = None,
          term_months: int | None = None) -> dict:
    """Факты заявки, по которым работают правила. Ничего не решает — только собирает."""
    rating = bureau.get_rating(db, app.company_id)
    score = rating.score if rating else None
    profile = app.business_profile or {}
    revenue = _num(profile.get("monthly_revenue"))
    debts = _num(profile.get("monthly_debt_payments")) or 0
    months = _num(profile.get("months_operating"))
    current = terms(app, amount, term_months, score)
    payment = current["monthly_payment"] or 0
    # Долговая нагрузка считается так же, как в блоке проверок карточки: вместе с новым платежом.
    load = (debts + payment) / revenue if revenue else None
    missing = [k for k in catalog.PROFILE_KEYS if _blank(profile.get(k))]
    need = required_months(current["amount"])
    return {
        **current,
        "borrowing_mode": app.borrowing_mode,
        "amount_rub": pricing.rub(current["amount"]) if current["amount"] else "—",
        "bureau_score": score,
        "rating_label": pricing.rating_band(score)[1] if score is not None else None,
        "monthly_revenue": revenue,
        "monthly_debt_payments": debts,
        # Пороги проверяются до округления: даже небольшое превышение меняет полосу.
        "debt_load_pct": load * 100 if load is not None else None,
        "debt_load_pct_text": str(round(load * 100)) if load is not None else None,
        "months_operating": months,
        "required_months": need,
        "months_operating_deficit": need - months if need is not None and months is not None else None,
        "profile_missing_count": len(missing),
        "profile_missing_labels": ", ".join(catalog.PROFILE_LABELS[k] for k in missing),
        "amount_to_revenue": current["amount"] / revenue
        if revenue and current["amount"] else None,
    }


# ---------- расчёт ----------

def _matching_band(rule: Rule, value) -> Band:
    for band in rule.bands:
        if value is None and band.op != "is_none":
            continue  # сравнивать нечего: для отсутствующего значения есть своя полоса
        if OPS[band.op](value, band.limit):
            return band
    # Полоса `any` есть у каждого правила; это страховка от правила без неё.
    return Band("any", None, 0, False, "Правило не применялось")


def _recommendation(total: int) -> str:
    for threshold, recommendation in RECOMMENDATION_BANDS:
        if threshold is None or total >= threshold:
            return recommendation
    return RECOMMENDATION_WHEN_DATA_MISSING


def rule_view(rule: Rule, band: Band, known: dict) -> dict:
    """Разбор одного правила для сотрудника: что требовалось, выполнено ли, сколько дало."""
    code = band.suggested_reject_reason_code
    return {
        "key": rule.key,
        "title": rule.title,
        "fired": band.ok,
        "contribution": band.points,
        "details": band.details.format(**known),
        "suggested_reject_reason_code": code,
        "suggested_reject_reason_text": catalog.REJECT_REASONS.get(code) if code else None,
    }


def apply_rules(known: dict, ruleset: tuple[Rule, ...] | None = None,
                version: str | None = None) -> dict:
    """Применяет набор правил к фактам. Чистая функция: ни базы, ни запроса, ни заявки.

    Логика расчёта не знает ни одного правила по имени — добавление правила в
    `RULESET` не требует правок здесь.
    """
    rules = ruleset if ruleset is not None else RULESET
    total = BASE_SCORE
    blocked = False
    breakdown = []
    for rule in rules:
        band = _matching_band(rule, known.get(rule.fact))
        total += band.points
        blocked = blocked or band.blocks_decision
        breakdown.append(rule_view(rule, band, known))
    total = max(SCORE_MIN, min(SCORE_MAX, total))
    recommendation = RECOMMENDATION_WHEN_DATA_MISSING if blocked else _recommendation(total)
    return {
        "ruleset_version": version if version is not None else RULESET_VERSION,
        "base_score": BASE_SCORE,
        "total_score": total,
        "score_min": SCORE_MIN,
        "score_max": SCORE_MAX,
        "recommendation": recommendation,
        "recommendation_label": RECOMMENDATION_LABELS[recommendation],
        "data_incomplete": blocked,
        "rules": breakdown,
        "facts": known,
    }


def evaluate(db: Session, app: Application, amount: int | None = None,
             term_months: int | None = None, ruleset: tuple[Rule, ...] | None = None,
             version: str | None = None) -> dict:
    """Живая оценка заявки: факты сейчас, правила — текущей версии набора."""
    return {
        "application_id": app.id,
        **apply_rules(facts(db, app, amount, term_months), ruleset, version),
    }


# ---------- снимки ----------

def snapshots(db: Session, application_id: int) -> list[ScoreSnapshot]:
    return list(db.scalars(
        select(ScoreSnapshot).where(ScoreSnapshot.application_id == application_id)
        .order_by(ScoreSnapshot.id)
    ))


def latest_snapshot(db: Session, application_id: int,
                    reason: SnapshotReason | None = None) -> ScoreSnapshot | None:
    stmt = select(ScoreSnapshot).where(ScoreSnapshot.application_id == application_id)
    if reason is not None:
        stmt = stmt.where(ScoreSnapshot.reason == reason)
    return db.scalars(stmt.order_by(ScoreSnapshot.id.desc())).first()


def take_snapshot(db: Session, app: Application, reason: SnapshotReason) -> ScoreSnapshot:
    """Фиксирует оценку целиком: баллы, рекомендацию, разбор по правилам и версию набора.

    Снимок не правится и не переписывается — так разбор вчерашнего решения остаётся
    тем, каким его видел сотрудник, даже если правила потом изменятся.
    """
    evaluation = evaluate(db, app)
    snapshot = ScoreSnapshot(
        application_id=app.id,
        ruleset_version=evaluation["ruleset_version"],
        reason=reason,
        total_score=evaluation["total_score"],
        recommendation=evaluation["recommendation"],
        breakdown=evaluation,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def ensure_intake_snapshot(db: Session, app: Application) -> ScoreSnapshot | None:
    """Снимок при приёме заявки. Повторный вызов ничего не дублирует.

    Вызывается и при приёме в конвейер, и при открытии оценки: заявки, принятые
    в конвейер до появления снимков, получают свой снимок при первом же открытии.
    """
    existing = latest_snapshot(db, app.id)
    if existing is not None:
        return existing
    return take_snapshot(db, app, SnapshotReason.ON_INTAKE)


def is_decided(app: Application) -> bool:
    return Status(app.status) in DECIDED_STATUSES


def frozen_snapshot(db: Session, app: Application) -> ScoreSnapshot | None:
    """Снимок, которым оценка заявки зафиксирована, или None — если оценка живая.

    Решение вынесено — отдаём снимок решения: разбор не должен меняться задним числом.
    Заявка ещё в работе — отдаём живой расчёт: сведения по ней ещё могут измениться.
    """
    if not is_decided(app):
        return None
    return latest_snapshot(db, app.id, SnapshotReason.ON_DECISION) or latest_snapshot(db, app.id)


def snapshot_evaluation(snapshot: ScoreSnapshot) -> dict:
    """Разбор из снимка. Поля-колонки главнее содержимого JSON: они и есть зафиксированное."""
    stored = dict(snapshot.breakdown or {})
    recommendation = snapshot.recommendation
    stored.update(
        ruleset_version=snapshot.ruleset_version,
        total_score=snapshot.total_score,
        recommendation=recommendation,
    )
    stored.setdefault("recommendation_label", RECOMMENDATION_LABELS.get(recommendation, recommendation))
    return stored


def evaluated_at(snapshot: ScoreSnapshot | None, now: datetime) -> datetime:
    return snapshot.created_at if snapshot is not None else now
