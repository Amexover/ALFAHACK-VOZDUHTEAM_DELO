import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  ClipboardList,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { api, ApiError, date, money, percent } from "./api";
import { useResource, useSession } from "./context";
import {
  Badge,
  Busy,
  Button,
  ErrorBox,
  FieldError,
  Heading,
  History,
  Modal,
  TermsView,
} from "./ui";
import type { Application, Brief, Status } from "./types";
import { AssistantInvite } from "./assistant/entry";
const FILTERS = [
  ["", "Все"],
  ["IN_REVIEW", "На рассмотрении"],
  ["NEED_INFO", "Нужны сведения"],
  ["resolved", "Решённые"],
];
export function StaffQueue() {
  const [filter, setFilter] = useState(""),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState("");
  const params = new URLSearchParams();
  if (filter === "resolved")
    for (const x of ["APPROVED", "COUNTER_OFFER", "REJECTED", "COMPLETED"])
      params.append("status", x);
  else if (filter) params.set("status", filter);
  if (query) params.set("q", query);
  const r = useResource<{ items: Brief[]; counts: Record<string, number> }>(
    `/staff/applications?${params}`,
  );
  return (
    <>
      <Heading
        title="Заявки бизнеса"
        description="Одна очередь. Весь контекст для решения."
      >
        <Button variant="secondary" onClick={r.refresh}>
          <RefreshCw size={16} />
          Обновить
        </Button>
      </Heading>
      <div className="queue-tools">
        <div className="segments filter-segments" aria-label="Фильтр заявок">
          {FILTERS.map(([key, label]) => (
            <button
              key={key}
              className={filter === key ? "selected" : ""}
              onClick={() => setFilter(key)}
            >
              {label}
              {r.data && (
                <span>
                  {key === ""
                    ? Object.values(r.data.counts).reduce((x, y) => x + y, 0)
                    : key === "resolved"
                      ? [
                          "APPROVED",
                          "COUNTER_OFFER",
                          "REJECTED",
                          "COMPLETED",
                        ].reduce((x, k) => x + (r.data!.counts[k] || 0), 0)
                      : r.data.counts[key] || 0}
                </span>
              )}
            </button>
          ))}
        </div>
        <form
          className="search-field"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search);
          }}
        >
          <Search size={17} />
          <input
            aria-label="Поиск по компании или номеру"
            placeholder="Компания или номер заявки"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              if (!e.target.value) setQuery("");
            }}
          />
          <button type="submit" className="text-button">
            Найти
          </button>
        </form>
      </div>
      {r.loading ? (
        <Busy />
      ) : r.error ? (
        <ErrorBox error={r.error} retry={r.refresh} />
      ) : !r.data?.items.length ? (
        <section className="panel empty">
          <ClipboardList size={32} />
          <h2>
            {query || filter
              ? "По этим условиям заявок нет"
              : "Пока нет отправленных заявок"}
          </h2>
          <p>
            {query || filter
              ? "Попробуйте другой запрос или фильтр."
              : "Когда клиент отправит заявку, она появится здесь."}
          </p>
          {(query || filter) && (
            <Button
              variant="text"
              onClick={() => {
                setFilter("");
                setQuery("");
                setSearch("");
              }}
            >
              Сбросить фильтры
            </Button>
          )}
        </section>
      ) : (
        <div className="panel table-panel">
          <div className="table-scroll">
            <table>
              <caption className="sr-only">
                Отправленные заявки клиентов
              </caption>
              <thead>
                <tr>
                  <th>Заявка и компания</th>
                  <th>Задача</th>
                  <th>Сумма</th>
                  <th>Статус</th>
                  <th>Подана</th>
                  <th>
                    <span className="sr-only">Открыть</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.data.items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <Link
                        to={`/staff/applications/${a.id}`}
                        className="table-primary"
                      >
                        {a.number}
                      </Link>
                      <span>{a.company_name}</span>
                    </td>
                    <td>
                      {a.borrowing_mode === "REFINANCE"
                        ? "Рефинансирование"
                        : a.product_name}
                    </td>
                    <td className="nowrap">{money(a.amount)}</td>
                    <td>
                      <Badge app={a} />
                    </td>
                    <td className="nowrap muted">
                      {date(a.submitted_at, true)}
                    </td>
                    <td>
                      <Link
                        className="icon-button"
                        aria-label={`Открыть заявку ${a.number}`}
                        to={`/staff/applications/${a.id}`}
                      >
                        <ArrowUpRight size={19} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
const ACTIONS: Record<string, string> = {
  "request-info": "Запросить сведения",
  approve: "Одобрить",
  "counter-offer": "Предложить другие условия",
  reject: "Отказать",
};
export function StaffCard() {
  const { id } = useParams(),
    r = useResource<Application>(`/staff/applications/${id}`),
    { config } = useSession();
  const [action, setAction] = useState<string | null>(null);
  if (r.loading) return <Busy />;
  if (r.error) return <ErrorBox error={r.error} retry={r.refresh} />;
  const a = r.data!;
  return (
    <>
      <Heading
        title={a.number || "Заявка"}
        description={`${a.company.name} · ${a.client?.full_name || ""}`}
        back="/staff"
      >
        <Button variant="secondary" onClick={r.refresh}>
          <RefreshCw size={16} />
          Обновить
        </Button>
      </Heading>
      <AssistantInvite application={a.id} staff />
      <div className="staff-layout">
        <div className="staff-main">
          <section className="panel">
            <div className="section-title">
              <h2>Запрос клиента</h2>
              <Badge app={a} />
            </div>
            <p className="muted">
              {a.borrowing_mode_label} ·{" "}
              {a.product_name || a.existing_loan?.name}
            </p>
            <TermsView
              terms={{
                amount: a.amount!,
                term_months: a.term_months!,
                rate: a.preliminary_rate!,
                monthly_payment: a.preliminary_payment!,
              }}
            />
            {a.existing_loan && (
              <p className="notice small">
                Текущий кредит: остаток {money(a.existing_loan.balance)}, ставка{" "}
                {percent(a.existing_loan.rate)}, платёж{" "}
                {money(a.existing_loan.next_payment_amount)}.
              </p>
            )}
            <dl className="profile-review">
              {config!.profile_fields.map((f) => (
                <div key={f.key}>
                  <dt>{f.label}</dt>
                  <dd>
                    {a.business_profile[f.key]?.toLocaleString("ru-RU") ?? "—"}{" "}
                    {f.unit}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="panel">
            <h2>Результаты проверок</h2>
            <p className="muted small">
              Локальные симуляторы. Реальные источники не запрашиваются.
            </p>
            <div className="staff-checks">
              {a.checks?.map((c) => (
                <div key={c.key}>
                  <CheckCircle2
                    size={20}
                    className={c.status === "OK" ? "check-ok" : "check-warn"}
                  />
                  <div>
                    <h3>{c.label}</h3>
                    <p>{c.details}</p>
                  </div>
                  <span
                    className={`check-label ${c.status === "OK" ? "check-ok" : "check-warn"}`}
                  >
                    {c.status === "OK"
                      ? "Проверено"
                      : c.status === "UNAVAILABLE"
                        ? "Нет данных"
                        : "Внимание"}
                  </span>
                </div>
              ))}
            </div>
          </section>
          {!!a.info_requests?.length && (
            <section className="panel">
              <h2>Уточнения клиента</h2>
              {a.info_requests.map((q) => (
                <div className="correspondence" key={q.id}>
                  <strong>{q.message}</strong>
                  <p className="small muted">{q.created_by}</p>
                  {q.answer_text ? (
                    <>
                      <p className="response-text">{q.answer_text}</p>
                      <dl className="profile-review">
                        {Object.entries(q.answer_fields || {}).map(
                          ([key, val]) => (
                            <div key={key}>
                              <dt>
                                {config!.profile_fields.find(
                                  (f) => f.key === key,
                                )?.label || key}
                              </dt>
                              <dd>{val?.toLocaleString("ru-RU") ?? "—"}</dd>
                            </div>
                          ),
                        )}
                      </dl>
                    </>
                  ) : (
                    <p className="muted">Ожидаем ответ клиента.</p>
                  )}
                </div>
              ))}
            </section>
          )}
          {a.decision && (
            <section className="panel">
              <h2>Решение: {a.decision.kind_label}</h2>
              {a.decision.kind !== "REJECTED" && (
                <TermsView terms={a.decision} />
              )}
              <p>{a.decision.reason_text}</p>
              <p className="pre-line">{a.decision.comment}</p>
            </section>
          )}
          <History app={a} />
        </div>
        <aside className="staff-aside">
          <section className="panel recommendation">
            <ShieldCheck size={24} />
            <h2>Рекомендация системы</h2>
            <strong className="recommendation-title">
              {a.scoring?.recommendation_label}
            </strong>
            {a.scoring?.reasons.map((s, i) => (
              <p key={i}>{s}</p>
            ))}
            <dl className="quote-rows">
              <div>
                <dt>Рейтинг бюро</dt>
                <dd>{a.rating?.score ?? "Недоступен"}</dd>
              </div>
              <div>
                <dt>Долговая нагрузка</dt>
                <dd>{percent(a.scoring?.debt_load_pct)}</dd>
              </div>
            </dl>
            <p className="small muted">
              Рекомендация помогает при рассмотрении. Итоговое решение принимает
              сотрудник.
            </p>
          </section>
          <section className="panel staff-actions">
            <h2>Действия по заявке</h2>
            {a.staff_actions?.length ? (
              <>
                {Object.entries(ACTIONS)
                  .filter(([key]) =>
                    a.staff_actions!.includes(key.replaceAll("-", "_")),
                  )
                  .map(([key, name]) => (
                    <Button
                      variant={key === "approve" ? "primary" : "secondary"}
                      key={key}
                      onClick={() => setAction(key)}
                    >
                      {name}
                    </Button>
                  ))}
                <p className="small muted">
                  Перед сохранением вы проверите и подтвердите решение.
                </p>
              </>
            ) : (
              <p className="muted small">
                Для статуса «{a.status_label}» новые решения недоступны.
              </p>
            )}
          </section>
        </aside>
      </div>
      {action && (
        <StaffDecision
          key={action}
          app={a}
          action={action}
          onClose={() => setAction(null)}
          onSaved={(updated) => {
            r.setData(updated);
            setAction(null);
          }}
        />
      )}
    </>
  );
}
function StaffDecision({
  app: a,
  action,
  onClose,
  onSaved,
}: {
  app: Application;
  action: string;
  onClose: () => void;
  onSaved: (a: Application) => void;
}) {
  const { config } = useSession(),
    reasons = useResource<{ items: { code: string; text: string }[] }>(
      action === "reject" ? "/staff/reject-reasons" : null,
    );
  const [comment, setComment] = useState(""),
    [amount, setAmount] = useState(String(a.amount)),
    [term, setTerm] = useState(String(a.term_months)),
    [rate, setRate] = useState(String(a.preliminary_rate)),
    [reason, setReason] = useState(""),
    [fields, setFields] = useState<string[]>([]),
    [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  function payload() {
    if (action === "request-info")
      return { message: comment, requested_fields: fields };
    if (action === "reject") return { reason_code: reason, comment };
    if (action === "counter-offer")
      return {
        amount: Number(amount),
        term_months: Number(term),
        rate: Number(rate.replace(",", ".")),
        comment,
      };
    return { comment };
  }
  async function save() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await api<Application>(
          `/staff/applications/${a.id}/${action}`,
          "POST",
          payload(),
        ),
      );
    } catch (e) {
      setError(e as Error);
      setConfirm(false);
    } finally {
      setBusy(false);
    }
  }
  function review(e: FormEvent) {
    e.preventDefault();
    if (!comment.trim()) {
      setError(new ApiError(422, "Укажите причину или точный вопрос клиенту."));
      return;
    }
    setError(null);
    setConfirm(true);
  }
  return (
    <Modal
      title={confirm ? "Подтвердите действие" : ACTIONS[action]}
      onClose={() => !busy && onClose()}
    >
      <p className="small muted">
        {a.number} · {a.company.name}
      </p>
      {confirm ? (
        <>
          <div className="confirmation-summary">
            <h3>{ACTIONS[action]}</h3>
            {action === "approve" && (
              <TermsView
                terms={{
                  amount: a.amount!,
                  term_months: a.term_months!,
                  rate: a.preliminary_rate!,
                  monthly_payment: a.preliminary_payment!,
                }}
              />
            )}
            {action === "counter-offer" && (
              <dl className="terms">
                <div>
                  <dt>Сумма</dt>
                  <dd>{money(Number(amount))}</dd>
                </div>
                <div>
                  <dt>Срок</dt>
                  <dd>{term} мес.</dd>
                </div>
                <div>
                  <dt>Ставка</dt>
                  <dd>{rate} %</dd>
                </div>
              </dl>
            )}
            {action === "reject" && (
              <p>{reasons.data?.items.find((x) => x.code === reason)?.text}</p>
            )}
            <p className="pre-line">{comment}</p>
            {fields.length > 0 && (
              <p className="small muted">
                Уточнить:{" "}
                {fields
                  .map(
                    (k) =>
                      config!.profile_fields.find((f) => f.key === k)?.label,
                  )
                  .join(", ")}
              </p>
            )}
          </div>
          <div className="actions">
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => setConfirm(false)}
            >
              Изменить
            </Button>
            <Button
              variant={action === "reject" ? "danger" : "primary"}
              busy={busy}
              onClick={save}
            >
              Подтвердить
            </Button>
          </div>
        </>
      ) : (
        <form onSubmit={review}>
          {action === "counter-offer" && (
            <div className="form-grid">
              <label className="field">
                Сумма, ₽
                <input
                  type="number"
                  value={amount}
                  min={config!.amount.min}
                  max={
                    a.borrowing_mode === "REFINANCE"
                      ? a.existing_loan!.balance
                      : a.company.max_amount
                  }
                  step={
                    a.borrowing_mode === "REFINANCE" ? 1 : config!.amount.step
                  }
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
                <FieldError error={error} name="amount" />
              </label>
              <label className="field">
                Срок, мес.
                <input
                  type="number"
                  value={term}
                  min={config!.term.min}
                  max={config!.term.max}
                  onChange={(e) => setTerm(e.target.value)}
                  required
                />
                <FieldError error={error} name="term_months" />
              </label>
              <label className="field">
                Ставка, % годовых
                <input
                  type="number"
                  value={rate}
                  min={1}
                  max={60}
                  step={0.1}
                  onChange={(e) => setRate(e.target.value)}
                  required
                />
                <FieldError error={error} name="rate" />
              </label>
            </div>
          )}
          {action === "approve" && (
            <>
              <p className="notice small">
                Одобрение подтверждает запрошенные параметры. Для изменения
                суммы, срока или ставки выберите «Предложить другие условия».
              </p>
              <TermsView
                terms={{
                  amount: a.amount!,
                  term_months: a.term_months!,
                  rate: a.preliminary_rate!,
                  monthly_payment: a.preliminary_payment!,
                }}
              />
            </>
          )}
          {action === "reject" &&
            (reasons.loading ? (
              <Busy />
            ) : reasons.error ? (
              <ErrorBox error={reasons.error} retry={reasons.refresh} />
            ) : (
              <label className="field">
                Причина отказа
                <select
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                >
                  <option value="">Выберите причину</option>
                  {reasons.data?.items.map((x) => (
                    <option value={x.code} key={x.code}>
                      {x.text}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          <label className="field">
            {action === "request-info"
              ? "Что нужно уточнить?"
              : "Пояснение клиенту"}
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={4}
              maxLength={action === "request-info" ? 4000 : 2000}
              required
            />
          </label>
          {action === "request-info" && (
            <fieldset className="request-fields">
              <legend>Какие поля должен заполнить клиент</legend>
              {config!.profile_fields.map((f) => (
                <label className="checkbox-line" key={f.key}>
                  <input
                    type="checkbox"
                    checked={fields.includes(f.key)}
                    onChange={(e) =>
                      setFields((x) =>
                        e.target.checked
                          ? [...x, f.key]
                          : x.filter((k) => k !== f.key),
                      )
                    }
                  />
                  {f.label}
                </label>
              ))}
              <p className="small muted">
                Если поля не выбраны, клиент ответит текстом.
              </p>
            </fieldset>
          )}
          <ErrorBox error={error} />
          <div className="actions">
            <Button variant="secondary" type="button" onClick={onClose}>
              Отмена
            </Button>
            <Button
              disabled={action === "reject" && (!reason || !!reasons.error)}
            >
              Проверить действие
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
