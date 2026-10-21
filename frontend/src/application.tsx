import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, RefreshCw } from "lucide-react";
import { api, ApiError, date, money } from "./api";
import { useResource, useSession } from "./context";
import {
  Badge,
  Busy,
  Button,
  ErrorBox,
  Heading,
  History,
  Modal,
  Progress,
  TermsView,
  applicationUrl,
} from "./ui";
import { ProfileInputs, profileBody, profileStrings } from "./wizard";
import type { Application } from "./types";
export function ApplicationPage() {
  const { id } = useParams(),
    r = useResource<Application>(`/applications/${id}`),
    { config } = useSession();
  const [error, setError] = useState<Error | null>(null),
    [busy, setBusy] = useState(false),
    [accepting, setAccepting] = useState(false),
    [supplement, setSupplement] = useState(false),
    [answer, setAnswer] = useState(""),
    [values, setValues] = useState<Record<string, string>>({});
  if (r.loading) return <Busy />;
  if (r.error) return <ErrorBox error={r.error} retry={r.refresh} />;
  const a = r.data!;
  if (a.status === "DRAFT")
    return (
      <>
        <Heading
          title="Заявка ещё не отправлена"
          description="Продолжите заполнение с сохранённого шага."
        />
        <Link className="button primary" to={applicationUrl(a)}>
          Продолжить заполнение
        </Link>
      </>
    );
  async function action(kind: string, body?: unknown) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api<Application>(
        `/applications/${id}/${kind}`,
        "POST",
        body,
      );
      r.setData(updated);
      setAccepting(false);
      setSupplement(false);
      setAnswer("");
      setValues({});
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function respond(e: FormEvent) {
    e.preventDefault();
    const fields = config!.profile_fields.filter((f) =>
      supplement
        ? values[f.key] !== undefined
        : a.info_request?.requested_fields.some((x) => x.key === f.key),
    );
    const required = supplement ? [] : fields;
    const missing = required.filter((f) => !values[f.key]?.trim());
    if (missing.length) {
      setError(
        new ApiError(
          422,
          "Заполните запрошенные сведения.",
          Object.fromEntries(
            missing.map((f) => ["fields." + f.key, "Заполните это поле"]),
          ),
        ),
      );
      return;
    }
    await action(supplement ? "supplement" : "info-response", {
      answer_text: answer,
      fields: profileBody(values, fields),
    });
  }
  const positive = a.status === "APPROVED" || a.status === "COUNTER_OFFER",
    d = a.decision;
  return (
    <>
      <Heading
        title={
          a.status === "COMPLETED"
            ? "Условия приняты"
            : a.status === "NEED_INFO"
              ? "Нужно уточнить сведения"
              : a.number || "Ваша заявка"
        }
        description={`${a.company.name} · ${date(a.submitted_at, true)}`}
        back={`/companies/${a.company_id}`}
      >
        <Button variant="secondary" onClick={r.refresh}>
          <RefreshCw size={16} />
          Обновить статус
        </Button>
      </Heading>
      <section
        className={`panel status-panel ${a.status === "COMPLETED" ? "completed" : ""}`}
      >
        <div className="row">
          <span>{a.number}</span>
          <Badge app={a} />
        </div>
        {a.status === "COMPLETED" && (
          <CheckCircle2 size={40} strokeWidth={1.4} className="success-icon" />
        )}
        <h2>
          {a.status === "COMPLETED"
            ? "Следующий шаг — за вашим бизнесом."
            : a.status === "REJECTED"
              ? "По этой заявке — отказ."
              : a.status === "APPROVED"
                ? "Банк одобрил вашу заявку."
                : a.status === "COUNTER_OFFER"
                  ? "У банка есть предложение."
                  : a.status === "NEED_INFO"
                    ? "Дополните заявку — и продолжим."
                    : "Заявка у банка. Всё на своём месте."}
        </h2>
        <p className="muted">{a.next_steps_text}</p>
        <Progress app={a} />
      </section>
      {a.status === "NEED_INFO" && a.info_request && (
        <section className="panel response-panel">
          <h2>Запрос банка</h2>
          <p className="request-text">{a.info_request.message}</p>
          <form onSubmit={respond}>
            <ProfileInputs
              fields={config!.profile_fields.filter((f) =>
                a.info_request!.requested_fields.some((x) => x.key === f.key),
              )}
              values={values}
              onChange={(k, v) => setValues((x) => ({ ...x, [k]: v }))}
              error={error}
              prefix="fields."
            />
            <label className="field">
              Ваш ответ
              <textarea
                rows={4}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                maxLength={4000}
                required
              />
            </label>
            <ErrorBox error={error} />
            <Button busy={busy}>Отправить сведения</Button>
          </form>
        </section>
      )}
      {d && (
        <section className="panel decision-panel">
          <h2>
            {a.status === "COMPLETED" ? "Принятые условия" : d.kind_label}
          </h2>
          {d.kind === "REJECTED" ? (
            <>
              <p>{d.reason_text}</p>
              {d.comment && <p className="muted pre-line">{d.comment}</p>}
            </>
          ) : (
            <>
              {d.kind === "COUNTER_OFFER" ? (
                <div className="offer-comparison">
                  <div>
                    <h3>Вы запрашивали</h3>
                    <TermsView terms={d.requested} />
                  </div>
                  <div>
                    <h3>Банк предлагает</h3>
                    <TermsView terms={d} />
                  </div>
                </div>
              ) : (
                <TermsView terms={d} />
              )}
              <p className="pre-line">{d.comment}</p>
              {d.refinance_remainder_text && (
                <p className="notice warning">{d.refinance_remainder_text}</p>
              )}
              {a.status === "COMPLETED" ? (
                <p className="notice">
                  Принято {date(a.completed_at, true)}. Демонстрационный путь
                  завершён. Подписание и выдача денег не моделируются.
                </p>
              ) : (
                <p className="small muted">
                  Это итоговые условия предложения банка. Принятие завершит
                  демонстрационный путь.
                </p>
              )}
            </>
          )}
          {positive && (
            <div className="actions">
              <Button
                onClick={() => {
                  setError(null);
                  setAccepting(true);
                }}
              >
                {a.status === "COUNTER_OFFER"
                  ? "Принять новые условия"
                  : "Принять условия"}
              </Button>
              {a.available_actions.includes("supplement") && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setError(null);
                    setSupplement(true);
                    setValues({});
                  }}
                >
                  Вернуться к заявке
                </Button>
              )}
            </div>
          )}
        </section>
      )}
      <section className="panel application-details">
        <h2>Данные заявки</h2>
        <p className="muted">
          {a.borrowing_mode_label} · {a.product_name || a.existing_loan?.name}
        </p>
        <TermsView
          terms={{
            amount: a.amount!,
            term_months: a.term_months!,
            rate: a.preliminary_rate!,
            monthly_payment: a.preliminary_payment!,
          }}
        />
        <details className="profile-disclosure">
          <summary>Сведения о бизнесе</summary>
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
        </details>
      </section>
      <History app={a} />
      <div className="page-bottom">
        <Link className="link" to={`/companies/${a.company_id}`}>
          <ArrowLeft size={16} />
          На главную
        </Link>
      </div>
      {accepting && (
        <Modal
          title="Принять предложение банка?"
          onClose={() => !busy && setAccepting(false)}
        >
          <p>
            {a.number} · {a.company.name}
          </p>
          <TermsView terms={d!} />
          <p className="small muted">
            Подписание и перевод денег не выполняются. Вы подтверждаете только
            демонстрационные условия.
          </p>
          <ErrorBox error={error} />
          <div className="actions">
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => setAccepting(false)}
            >
              Вернуться
            </Button>
            <Button busy={busy} onClick={() => action("accept")}>
              Подтвердить принятие
            </Button>
          </div>
        </Modal>
      )}
      {supplement && (
        <Modal
          title="Дополнить заявку"
          onClose={() => !busy && setSupplement(false)}
        >
          <p className="muted">
            Текущее предложение аннулируется. Банк рассмотрит заявку заново с
            учётом вашего дополнения.
          </p>
          <form onSubmit={respond}>
            <label className="field">
              Что вы хотите дополнить?
              <textarea
                rows={3}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                maxLength={4000}
                required
              />
            </label>
            <ProfileInputs
              fields={config!.profile_fields}
              values={values}
              onChange={(k, v) => setValues((x) => ({ ...x, [k]: v }))}
              error={error}
              required={false}
              prefix="fields."
            />
            <ErrorBox error={error} />
            <Button busy={busy}>Отправить на повторное рассмотрение</Button>
          </form>
        </Modal>
      )}
    </>
  );
}
