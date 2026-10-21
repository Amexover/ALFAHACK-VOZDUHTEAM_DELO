"""Справочники и тексты. Названия — без переименований (инструкция, §15)."""

from app.enums import BorrowingMode, DecisionKind, EventType, LegalForm, ProductId, Status

PRODUCTS = {
    ProductId.WORKING_CAPITAL: {
        "product_id": ProductId.WORKING_CAPITAL.value,
        "card_title": "Закупки и текущие расходы",
        "name": "Оборотный кредит",
        "description": "Разовая сумма на закупку товаров, сырья и другие текущие расходы бизнеса. "
        "Возврат равными ежемесячными платежами.",
    },
    ProductId.EQUIPMENT: {
        "product_id": ProductId.EQUIPMENT.value,
        "card_title": "Покупка оборудования",
        "name": "Кредит на оборудование",
        "description": "Разовая сумма на станки, технику и рабочее оборудование. "
        "Возврат равными ежемесячными платежами.",
    },
}

BORROWING_MODES = {
    BorrowingMode.NEW_CREDIT: {"borrowing_mode": "NEW_CREDIT", "button_label": "Новый кредит", "name": "Новый кредит"},
    BorrowingMode.REFINANCE: {
        "borrowing_mode": "REFINANCE",
        "button_label": "Рефинансирование",
        "name": "Рефинансирование действующего кредита",
    },
}

LEGAL_FORMS = {
    LegalForm.OOO: {"legal_form": "OOO", "label": "ООО", "registration_label": "ОГРН", "registration_length": 13},
    LegalForm.IP: {"legal_form": "IP", "label": "ИП", "registration_label": "ОГРНИП", "registration_length": 15},
}

STATUS_LABELS = {
    Status.DRAFT: "Черновик",
    Status.IN_REVIEW: "На рассмотрении",
    Status.NEED_INFO: "Нужно уточнить сведения",
    Status.APPROVED: "Одобрено",
    Status.COUNTER_OFFER: "Предложены другие условия",
    Status.REJECTED: "Отказ",
    Status.COMPLETED: "Условия приняты",
}

NEXT_STEPS = {
    Status.DRAFT: "Заполните заявку и отправьте её на рассмотрение.",
    Status.IN_REVIEW: "Проверяем данные. Пока от вас ничего не требуется.",
    Status.NEED_INFO: "Нужно уточнить сведения. Ответьте на вопрос банка на этой странице.",
    Status.APPROVED: "Банк одобрил заявку. Проверьте итоговые условия и примите их.",
    Status.COUNTER_OFFER: "Банк предлагает другие условия. Сравните их с запрошенными: примите или дополните заявку.",
    Status.REJECTED: "Банк не может одобрить заявку. Объяснение — ниже.",
    Status.COMPLETED: "Условия приняты. Подписание договора и выдача денег в демонстрации не моделируются.",
}

STAGES = [
    ("SUBMITTED", "Заявка отправлена"),
    ("CHECK", "Проверка данных"),
    ("DECISION", "Решение"),
    ("COMPLETION", "Завершение"),
]

STAGE_INDEX = {
    Status.DRAFT: -1,
    Status.IN_REVIEW: 1,
    Status.NEED_INFO: 1,
    Status.APPROVED: 2,
    Status.COUNTER_OFFER: 2,
    Status.REJECTED: 2,
    Status.COMPLETED: 3,
}

EVENT_LABELS = {
    EventType.SUBMITTED: "Заявка отправлена",
    EventType.INFO_REQUESTED: "Банк запросил сведения",
    EventType.INFO_PROVIDED: "Клиент отправил сведения",
    EventType.APPROVED: "Заявка одобрена",
    EventType.COUNTER_OFFERED: "Банк предложил другие условия",
    EventType.REJECTED: "Отказ по заявке",
    EventType.SUPPLEMENTED: "Клиент дополнил заявку",
    EventType.ACCEPTED: "Клиент принял условия",
}

DECISION_LABELS = {
    DecisionKind.APPROVED: "Одобрено",
    DecisionKind.COUNTER_OFFER: "Предложены другие условия",
    DecisionKind.REJECTED: "Отказ",
}

# Поля анкеты бизнеса (экран 8). Ключи используются в business_profile,
# в запросах сведений (requested_fields) и в ответах клиента.
PROFILE_FIELDS = [
    {"key": "industry", "label": "Сфера деятельности", "type": "string", "unit": None,
     "hint": "Например: оптовая торговля, производство мебели"},
    {"key": "months_operating", "label": "Сколько месяцев работает бизнес", "type": "integer", "unit": "мес.",
     "hint": "Считая с даты регистрации"},
    {"key": "monthly_revenue", "label": "Среднемесячная выручка", "type": "integer", "unit": "₽",
     "hint": "Средняя выручка за последние 6–12 месяцев"},
    {"key": "monthly_debt_payments", "label": "Текущие ежемесячные платежи по долгам", "type": "integer", "unit": "₽",
     "hint": "Сумма платежей по всем кредитам и займам; 0, если долгов нет"},
    {"key": "purpose_details", "label": "Пояснение цели", "label_refinance": "Почему хотите изменить условия?",
     "type": "string", "unit": None, "hint": "Пара предложений своими словами"},
]
PROFILE_KEYS = [f["key"] for f in PROFILE_FIELDS]
PROFILE_LABELS = {f["key"]: f["label"] for f in PROFILE_FIELDS}

REJECT_REASONS = {
    "LOW_RATING": "Кредитная история компании пока не позволяет одобрить заявку на запрошенных условиях.",
    "HIGH_DEBT_LOAD": "Текущая долговая нагрузка бизнеса слишком высока для нового ежемесячного платежа.",
    "SHORT_HISTORY": "Бизнес работает недостаточно долго для запрошенной суммы.",
    "INSUFFICIENT_DATA": "Сведений в заявке недостаточно, чтобы принять положительное решение.",
}

RATING_SOURCE_LABEL = "Демонстрационные данные скорингового бюро"
RATING_HINT = (
    "Рейтинг влияет на предварительный расчёт ставки, но сам по себе не означает одобрение. "
    "Окончательное решение принимает банк после рассмотрения заявки."
)
RATING_UNAVAILABLE_TEXT = "Рейтинг пока недоступен"
PRELIMINARY_NOTE = "Условия предварительные и могут измениться после рассмотрения."
FINAL_TERMS_NOTE = "Окончательные условия появятся после рассмотрения заявки."
REFINANCE_COMPARISON_NOTE = "Оставшийся срок текущего кредита может отличаться, поэтому платежи сравниваются ориентировочно."
