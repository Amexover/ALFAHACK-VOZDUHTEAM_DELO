import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ClipboardCheck,
  FileCheck2,
  Landmark,
  Save,
} from "lucide-react";
import { api, ApiError, money, number, percent } from "./api";
import { useResource, useSession } from "./context";
import { Busy, Button, ErrorBox, FieldError, Heading, TermsView } from "./ui";
import type {
  Application,
  Config,
  Loan,
  Profile,
  ProfileField,
  ProfileKey,
} from "./types";
export const STEP_NAMES: Record<string, string> = {
  parameters: "Параметры кредита",
  product: "Для чего нужны деньги?",
  refinance_loan: "Какой кредит пересмотрим?",
  refinance_params: "Новые условия кредита",
  business: "Расскажите немного о бизнесе",
  checks: "Что проверит банк",
  review: "Проверьте заявку",
};
const newSteps = ["parameters", "product", "business", "checks", "review"],
  refSteps = [
    "refinance_loan",
    "refinance_params",
    "business",
    "checks",
    "review",
  ];
export function Wizard() {
  const { id, step = "parameters" } = useParams(),
    r = useResource<Application>(`/applications/${id}`),
    { config } = useSession();
  if (r.loading) return <Busy />;
  if (r.error) return <ErrorBox error={r.error} retry={r.refresh} />;
  const a = r.data!;
  if (a.status !== "DRAFT")
    return <Navigate replace to={`/applications/${id}`} />;
  const steps = a.borrowing_mode === "REFINANCE" ? refSteps : newSteps;
  if (!steps.includes(step))
    return <Navigate replace to={`/applications/${id}/edit/${steps[0]}`} />;
  return (
    <>
      <Heading
        title={STEP_NAMES[step]}
        description={a.company.name}
        back={`/companies/${a.company_id}`}
      />
      <ol className="wizard-steps" aria-label="Этапы заполнения">
        {steps.map((s, i) => (
          <li
            key={s}
            className={
              s === step ? "active" : steps.indexOf(step) > i ? "done" : ""
            }
            aria-current={s === step ? "step" : undefined}
          >
            <span>{steps.indexOf(step) > i ? <Check size={13} /> : i + 1}</span>
            <span>
              {i < 2
                ? i === 0
                  ? a.borrowing_mode === "REFINANCE"
                    ? "Кредит"
                    : "Условия"
                  : a.borrowing_mode === "REFINANCE"
                    ? "Условия"
                    : "Цель"
                : i === 2
                  ? "О бизнесе"
                  : i === 3
                    ? "Проверки"
                    : "Отправка"}
            </span>
          </li>
        ))}
      </ol>
      <WizardStep
        key={`${id}:${step}`}
        app={a}
        config={config!}
        step={step}
        steps={steps}
        onUpdate={r.setData}
      />
    </>
  );
}
export function ProfileInputs({
  fields,
  values,
  onChange,
  error,
  prefix = "business_profile.",
  required = true,
  refinance = false,
}: {
  fields: ProfileField[];
  values: Record<string, string>;
  onChange: (key: string, v: string) => void;
  error: Error | null;
  prefix?: string;
  required?: boolean;
  refinance?: boolean;
}) {
  return (
    <div className="profile-fields">
      {fields.map((f) => {
        const label =
          refinance && f.label_refinance ? f.label_refinance : f.label;
        const common = {
          id: `field-${f.key}`,
          value: values[f.key] ?? "",
          onChange: (
            e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
          ) => onChange(f.key, e.target.value),
          required,
          "aria-invalid":
            (error instanceof ApiError && !!error.fields[prefix + f.key]) ||
            undefined,
          "aria-describedby": `hint-${f.key}`,
        };
        return (
          <label
            className={`field ${f.key === "purpose_details" ? "wide" : ""}`}
            key={f.key}
            htmlFor={`field-${f.key}`}
          >
            <span>
              {label}
              {f.unit && <span className="muted">, {f.unit}</span>}
            </span>
            {f.key === "purpose_details" ? (
              <textarea {...common} rows={4} maxLength={2000} />
            ) : f.type === "integer" ? (
              <input
                {...common}
                inputMode="numeric"
                value={
                  values[f.key]
                    ? Number(values[f.key].replace(/\s/g, "")).toLocaleString(
                        "ru-RU",
                      )
                    : ""
                }
                onChange={(e) =>
                  onChange(f.key, e.target.value.replace(/\D/g, ""))
                }
              />
            ) : (
              <input {...common} maxLength={200} />
            )}
            <small id={`hint-${f.key}`}>{f.hint}</small>
            <FieldError error={error} name={prefix + f.key} />
          </label>
        );
      })}
    </div>
  );
}
export const profileStrings = (p: Profile) =>
  Object.fromEntries(
    Object.entries(p).map(([k, v]) => [k, v == null ? "" : String(v)]),
  );
export function profileBody(
  values: Record<string, string>,
  fields: ProfileField[],
): Profile {
  return Object.fromEntries(
    fields
      .filter((f) => values[f.key] !== undefined && values[f.key].trim() !== "")
      .map((f) => [
        f.key,
        f.type === "integer" ? Number(values[f.key]) : values[f.key].trim(),
      ]),
  ) as Profile;
}
function WizardStep({
  app: a,
  config: c,
  step,
  steps,
  onUpdate,
}: {
  app: Application;
  config: Config;
  step: string;
  steps: string[];
  onUpdate: (a: Application) => void;
}) {
  const nav = useNavigate(),
    [search] = useSearchParams(),
    [amount, setAmount] = useState(String(a.amount ?? c.amount.default)),
    [term, setTerm] = useState(String(a.term_months ?? c.term.default)),
    [product, setProduct] = useState(a.product_id || ""),
    [loanId, setLoanId] = useState(a.existing_loan?.id || 0),
    [profile, setProfile] = useState(profileStrings(a.business_profile)),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  const [quote, setQuote] = useState({
      key: JSON.stringify([Number(amount), Number(term), a.existing_loan?.id]),
      rate: a.preliminary_rate,
      payment: a.preliminary_payment,
      note: a.rating_note,
      comparison: a.comparison,
    }),
    [quoteBusy, setQuoteBusy] = useState(false),
    [quoteRetry, setQuoteRetry] = useState(0),
    [quoteError, setQuoteError] = useState<Error | null>(null);
  const loans = useResource<{ items: Loan[] }>(
    step === "refinance_loan" ? `/companies/${a.company_id}/loans` : null,
  );
  const quoteVersion = useRef(0);
  const refi = a.borrowing_mode === "REFINANCE",
    isParams = step === "parameters" || step === "refinance_params",
    isReturn = search.get("return") === "review",
    index = steps.indexOf(step);
  const quoteKey = JSON.stringify([
    Number(amount),
    Number(term),
    a.existing_loan?.id,
  ]);
  const validQuoteInputs =
    Number.isInteger(Number(term)) &&
    Number(term) >= c.term.min &&
    Number(term) <= c.term.max &&
    (refi
      ? !!a.existing_loan
      : Number.isInteger(Number(amount)) &&
        Number(amount) >= c.amount.min &&
        Number(amount) <= a.company.max_amount &&
        Number(amount) % c.amount.step === 0);
  const currentQuote =
    (!isParams || validQuoteInputs) && quote.key === quoteKey && !quoteError
      ? quote
      : null;
  useEffect(() => {
    if (!isParams) return;
    const requestId = ++quoteVersion.current;
    const n = Number(amount),
      t = Number(term);
    setQuoteError(null);
    if (!validQuoteInputs) {
      setQuoteBusy(false);
      return;
    }
    setQuoteBusy(true);
    const abort = new AbortController();
    const timer = setTimeout(() => {
      api<{
        rate: number;
        monthly_payment: number;
        preliminary_rate?: number;
        preliminary_payment?: number;
        rating_note?: string;
        rating_based?: boolean;
        comparison: Application["comparison"];
      }>(
        `/pricing/quote`,
        "POST",
        {
          company_id: a.company_id,
          borrowing_mode: a.borrowing_mode,
          term_months: t,
          ...(refi ? { existing_loan_id: a.existing_loan!.id } : { amount: n }),
        },
        abort.signal,
      )
        .then((q) => {
          if (requestId !== quoteVersion.current) return;
          setQuote({
            key: quoteKey,
            rate: q.preliminary_rate ?? q.rate,
            payment: q.preliminary_payment ?? q.monthly_payment,
            note: q.rating_note ?? null,
            comparison: q.comparison,
          });
          setQuoteError(null);
        })
        .catch((e) => {
          if (e.name !== "AbortError" && requestId === quoteVersion.current)
            setQuoteError(e);
        })
        .finally(() => {
          if (requestId === quoteVersion.current && !abort.signal.aborted)
            setQuoteBusy(false);
        });
    }, 300);
    return () => {
      clearTimeout(timer);
      abort.abort();
    };
  }, [amount, term, isParams, quoteRetry]);
  function payload() {
    if (isParams)
      return {
        ...(!refi ? { amount: Number(amount) } : {}),
        term_months: Number(term),
      };
    if (step === "product") return { product_id: product };
    if (step === "refinance_loan") return { existing_loan_id: loanId };
    if (step === "business")
      return { business_profile: profileBody(profile, c.profile_fields) };
    return {};
  }
  async function save(target: string, validate = false) {
    if (busy) return;
    setError(null);
    if (validate && step === "business") {
      const missing = Object.fromEntries(
        c.profile_fields
          .filter((f) => !profile[f.key]?.trim())
          .map((f) => [`business_profile.${f.key}`, "Заполните это поле"]),
      );
      if (Object.keys(missing).length) {
        setError(
          new ApiError(
            422,
            "Заполните обязательные сведения о бизнесе.",
            missing,
          ),
        );
        return;
      }
    }
    if (validate && step === "product" && !product) {
      setError(new ApiError(422, "Выберите цель финансирования."));
      return;
    }
    if (validate && step === "refinance_loan" && !loanId) {
      setError(new ApiError(422, "Выберите действующий кредит."));
      return;
    }
    setBusy(true);
    try {
      const nextStep = target.startsWith("/companies/")
        ? step
        : target.split("/").pop()!.split("?")[0];
      const updated = await api<Application>(`/applications/${a.id}`, "PATCH", {
        ...payload(),
        current_step: nextStep,
      });
      onUpdate(updated);
      nav(target);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await api<Application>(`/applications/${a.id}/submit`, "POST", {
        confirm_data: confirmed,
      });
      nav(`/applications/${a.id}`, { replace: true });
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  const forward = isReturn ? "review" : steps[index + 1],
    back = steps[index - 1],
    edit = (s: string) => `/applications/${a.id}/edit/${s}?return=review`;
  const sidebar = (
    <aside className="panel quote-panel">
      <h2>{refi ? "Предварительные условия" : "Ваш предварительный расчёт"}</h2>
      <p className="quote-amount">{money(refi ? a.amount : Number(amount))}</p>
      <dl className="quote-rows">
        <div>
          <dt>Срок</dt>
          <dd>{term || "—"} мес.</dd>
        </div>
        <div>
          <dt>Ставка</dt>
          <dd>
            {quoteBusy && validQuoteInputs
              ? "Считаем…"
              : percent(currentQuote?.rate)}
          </dd>
        </div>
        <div>
          <dt>Платёж в месяц</dt>
          <dd>
            {quoteBusy && validQuoteInputs
              ? "Считаем…"
              : money(currentQuote?.payment)}
          </dd>
        </div>
      </dl>
      {currentQuote?.note && <p className="small">{currentQuote.note}</p>}
      <ErrorBox
        error={quoteError}
        retry={() => setQuoteRetry((value) => value + 1)}
      />
      {isParams && !validQuoteInputs && (
        <p className="small muted">
          Укажите сумму и срок в допустимых пределах, чтобы увидеть расчёт.
        </p>
      )}
      <p className="small muted">{c.texts.preliminary_note}</p>
      <div className="quote-company">
        <BuildingMark />
        <div>
          <strong>{a.company.name}</strong>
          <small>
            {a.company.registration_label} {a.company.registration_number}
          </small>
        </div>
      </div>
    </aside>
  );
  return (
    <>
      <div
        className={`wizard-layout ${step === "review" || step === "checks" ? "single" : ""}`}
      >
        <section className="panel wizard-panel">
          {isParams && (
            <>
              {refi && (
                <>
                  <div className="notice">
                    <strong>
                      Остаток действующего кредита — {money(a.amount)}
                    </strong>
                    <p>
                      Сумма рефинансирования фиксирована. Выберите новый срок.
                    </p>
                  </div>
                  <h2>Как изменятся условия</h2>
                  <div className="refinance-before">
                    <span>
                      Сейчас: {percent(a.existing_loan?.rate)} годовых
                    </span>
                    <span>
                      Ближайший платёж:{" "}
                      {money(a.existing_loan?.next_payment_amount)}
                    </span>
                  </div>
                </>
              )}
              {!refi && (
                <div className="range-field">
                  <label htmlFor="amount-input">Сколько нужно бизнесу?</label>
                  <div className="amount-input-wrap">
                    <input
                      id="amount-input"
                      inputMode="numeric"
                      value={
                        amount ? Number(amount).toLocaleString("ru-RU") : ""
                      }
                      onChange={(e) =>
                        setAmount(e.target.value.replace(/\D/g, ""))
                      }
                      aria-describedby="amount-hint"
                    />
                    <span>₽</span>
                  </div>
                  <input
                    aria-label="Сумма кредита"
                    type="range"
                    min={c.amount.min}
                    max={a.company.max_amount}
                    step={c.amount.step}
                    value={amount || c.amount.min}
                    onChange={(e) => setAmount(e.target.value)}
                  />
                  <div className="range-ends" id="amount-hint">
                    <span>От {money(c.amount.min)}</span>
                    <span>До {money(a.company.max_amount)}</span>
                  </div>
                  <FieldError error={error} name="amount" />
                </div>
              )}
              <div className="range-field">
                <label htmlFor="term-input">На какой срок?</label>
                <div className="amount-input-wrap">
                  <input
                    id="term-input"
                    inputMode="numeric"
                    value={term}
                    onChange={(e) => setTerm(e.target.value.replace(/\D/g, ""))}
                  />
                  <span>месяцев</span>
                </div>
                <input
                  aria-label="Срок кредита"
                  type="range"
                  min={c.term.min}
                  max={c.term.max}
                  step={c.term.step}
                  value={term || c.term.min}
                  onChange={(e) => setTerm(e.target.value)}
                />
                <div className="range-ends">
                  <span>{c.term.min} месяцев</span>
                  <span>{c.term.max} месяцев</span>
                </div>
                <FieldError error={error} name="term_months" />
              </div>
              {refi && (
                <p className="notice small">
                  {currentQuote?.comparison?.is_better === false && (
                    <strong>
                      Предварительная ставка не ниже текущей. Обратите внимание
                      на условия.{" "}
                    </strong>
                  )}
                  {currentQuote?.comparison?.note} Сравнение ставки и платежа
                  носит предварительный характер. Меньший платёж сам по себе не
                  означает экономию.
                </p>
              )}
              <p className="save-hint">
                <Save size={14} />
                Параметры сохранятся при переходе к следующему шагу.
              </p>
            </>
          )}
          {step === "product" && (
            <>
              <div className="product-options">
                {c.products.map((p) => (
                  <label
                    key={p.product_id}
                    className={`product-option ${product === p.product_id ? "chosen" : ""}`}
                  >
                    <input
                      type="radio"
                      name="product"
                      value={p.product_id}
                      checked={product === p.product_id}
                      onChange={() => setProduct(p.product_id)}
                    />
                    <span className="product-icon">
                      {p.product_id === "EQUIPMENT" ? (
                        <Landmark size={26} />
                      ) : (
                        <ClipboardCheck size={26} />
                      )}
                    </span>
                    <strong>{p.card_title}</strong>
                    <span>{p.name}</span>
                    <p>{p.description}</p>
                  </label>
                ))}
              </div>
              <Link
                className="link"
                to={`/applications/${a.id}/edit/parameters`}
              >
                Изменить сумму и срок
              </Link>
            </>
          )}
          {step === "refinance_loan" &&
            (loans.loading ? (
              <Busy />
            ) : loans.error ? (
              <ErrorBox error={loans.error} retry={loans.refresh} />
            ) : (
              <fieldset className="business-options">
                <legend>Действующие кредиты компании</legend>
                {loans.data?.items.map((l) => {
                  const unavailable =
                    !!l.active_application_id &&
                    l.active_application_id !== a.id;
                  return (
                    <label
                      key={l.id}
                      className={`loan-choice ${loanId === l.id ? "chosen" : ""} ${unavailable ? "unavailable" : ""}`}
                    >
                      <div className="row">
                        <strong>{l.name}</strong>
                        <input
                          type="radio"
                          name="loan"
                          checked={loanId === l.id}
                          disabled={unavailable}
                          onChange={() => setLoanId(l.id)}
                        />
                      </div>
                      <dl className="terms">
                        <div>
                          <dt>Остаток долга</dt>
                          <dd>{money(l.balance)}</dd>
                        </div>
                        <div>
                          <dt>Текущая ставка</dt>
                          <dd>{percent(l.rate)}</dd>
                        </div>
                      </dl>
                      {unavailable && (
                        <p>По этому кредиту уже есть активная заявка.</p>
                      )}
                    </label>
                  );
                })}
              </fieldset>
            ))}
          {step === "business" && (
            <>
              <div className="company-readonly">
                <strong>{a.company.name}</strong>
                <p>
                  {a.company.registration_label} {a.company.registration_number}
                </p>
                <Link className="link small" to="/companies">
                  Выбрать другую компанию
                </Link>
              </div>
              <ProfileInputs
                fields={c.profile_fields}
                values={profile}
                onChange={(k, v) => setProfile((x) => ({ ...x, [k]: v }))}
                error={error}
                refinance={refi}
              />
            </>
          )}
          {step === "checks" && (
            <>
              <h2>Только нужные сведения</h2>
              <p className="muted">
                Проверки используют анкету и локальные демонстрационные данные.
              </p>
              <div className="check-list">
                {[
                  [
                    Landmark,
                    "Регистрация бизнеса",
                    "Проверим формат регистрационного номера в симуляторе реестра.",
                  ],
                  [
                    FileCheck2,
                    "Кредитная история",
                    "Используем демонстрационный рейтинг из локального симулятора бюро.",
                  ],
                  [
                    ClipboardCheck,
                    "Полнота анкеты",
                    "Убедимся, что все необходимые сведения заполнены.",
                  ],
                ].map(([Icon, title, text]) => {
                  const I = Icon as typeof Landmark;
                  return (
                    <div key={String(title)}>
                      <I size={23} />
                      <div>
                        <h3>{String(title)}</h3>
                        <p>{String(text)}</p>
                      </div>
                      <CheckCircle2 size={19} className="muted" />
                    </div>
                  );
                })}
              </div>
              <div className="notice">
                Реальные ФНС и кредитные бюро не запрашиваются. Загружать
                документы не нужно.
              </div>
            </>
          )}
          {step === "review" && (
            <>
              <div className="review-block">
                <div className="section-title">
                  <h2>Компания и задача</h2>
                  <Link
                    className="link"
                    to={edit(refi ? "refinance_loan" : "product")}
                  >
                    Изменить
                  </Link>
                </div>
                <strong>{a.company.name}</strong>
                <p className="muted">
                  {a.borrowing_mode_label} ·{" "}
                  {a.product_name || a.existing_loan?.name}
                </p>
              </div>
              <div className="review-block">
                <div className="section-title">
                  <h2>Условия</h2>
                  <Link
                    className="link"
                    to={edit(refi ? "refinance_params" : "parameters")}
                  >
                    Изменить
                  </Link>
                </div>
                <TermsView
                  terms={{
                    amount: a.amount!,
                    term_months: a.term_months!,
                    rate: a.preliminary_rate!,
                    monthly_payment: a.preliminary_payment!,
                  }}
                />
                <p className="small muted">{c.texts.final_terms_note}</p>
              </div>
              <div className="review-block">
                <div className="section-title">
                  <h2>О бизнесе</h2>
                  <Link className="link" to={edit("business")}>
                    Изменить
                  </Link>
                </div>
                <dl className="profile-review">
                  {c.profile_fields.map((f) => (
                    <div key={f.key}>
                      <dt>
                        {refi && f.label_refinance
                          ? f.label_refinance
                          : f.label}
                      </dt>
                      <dd>
                        {typeof a.business_profile[f.key] === "number"
                          ? number(a.business_profile[f.key] as number)
                          : a.business_profile[f.key] || "Не заполнено"}
                        {f.unit && a.business_profile[f.key] != null
                          ? " " + f.unit
                          : ""}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                <span>
                  Подтверждаю достоверность синтетических данных и согласие на
                  демонстрационную обработку.
                </span>
              </label>
            </>
          )}
          <ErrorBox error={error} />
          <div className="wizard-actions">
            <Button
              variant="text"
              disabled={busy}
              onClick={() =>
                save(
                  back
                    ? `/applications/${a.id}/edit/${back}`
                    : `/companies/${a.company_id}`,
                )
              }
            >
              <ArrowLeft size={16} />
              Назад
            </Button>
            <div>
              {step !== "review" && (
                <Button
                  variant="secondary"
                  busy={busy}
                  onClick={() => save(`/companies/${a.company_id}`)}
                >
                  Сохранить и выйти
                </Button>
              )}
              {step === "review" ? (
                <Button disabled={!confirmed} busy={busy} onClick={submit}>
                  Отправить заявку
                  <ArrowRight size={17} />
                </Button>
              ) : (
                <Button
                  busy={busy}
                  disabled={
                    step === "product"
                      ? !product
                      : step === "refinance_loan"
                        ? !loanId
                        : false
                  }
                  onClick={() =>
                    save(`/applications/${a.id}/edit/${forward}`, true)
                  }
                >
                  {isReturn ? "Сохранить изменения" : "Продолжить"}
                  <ArrowRight size={17} />
                </Button>
              )}
            </div>
          </div>
        </section>
        {step !== "review" && step !== "checks" && sidebar}
      </div>
    </>
  );
}
function BuildingMark() {
  return (
    <span className="quote-company-mark">
      <Landmark size={19} />
    </span>
  );
}
