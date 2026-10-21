import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  ChevronDown,
  HelpCircle,
  LogOut,
  Plus,
  RefreshCw,
  Wallet,
} from "lucide-react";
import { api, ApiError, date, money, number, percent } from "./api";
import { useResource, useSession } from "./context";
import {
  ApplicationLink,
  Badge,
  Busy,
  Button,
  ErrorBox,
  FieldError,
  Heading,
  Modal,
  Progress,
  applicationUrl,
} from "./ui";
import type {
  Company,
  Dashboard,
  News,
  User,
  Brief,
  Mode,
  Application,
} from "./types";
export function Login() {
  const { setUser } = useSession(),
    nav = useNavigate();
  const [login, setLogin] = useState("alexey"),
    [password, setPassword] = useState("demo"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const d = await api<{ user: User }>("/auth/login", "POST", {
        login,
        password,
      });
      setUser(d.user);
      nav(d.user.role === "EMPLOYEE" ? "/staff" : "/companies", {
        replace: true,
      });
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <Link to="/" className="brand">
        дело<span>.</span>
      </Link>
      <div className="login-layout">
        <div className="login-intro">
          <h1>
            Большие планы.
            <br />
            Простое начало.
          </h1>
          <p>
            Кредитный кабинет, в котором
            <br />
            понятен каждый следующий шаг.
          </p>
          <div className="login-foot">
            Демонстрационная версия
            <br />
            <span>Все данные вымышлены. Реальные кредиты не выдаются.</span>
          </div>
        </div>
        <section className="panel login-form">
          <h2>Войти в кабинет</h2>
          <p className="muted">Выберите роль для знакомства с сервисом.</p>
          <div className="segments" aria-label="Роль в демонстрации">
            {[
              ["alexey", "Клиент"],
              ["staff", "Сотрудник"],
            ].map(([id, name]) => (
              <button
                type="button"
                key={id}
                className={login === id ? "selected" : ""}
                onClick={() => {
                  setLogin(id);
                  setPassword("demo");
                  setError(null);
                }}
              >
                {name}
              </button>
            ))}
          </div>
          <form onSubmit={submit}>
            <label className="field">
              Логин
              <input
                autoComplete="username"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                required
              />
            </label>
            <label className="field">
              Пароль
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <ErrorBox error={error} />
            <Button type="submit" busy={busy} className="full">
              Войти
              <ArrowRight size={18} />
            </Button>
          </form>
          <details className="demo-accounts">
            <summary>Демонстрационные учётные записи</summary>
            <p>
              Клиенты: <b>alexey</b> и <b>maria</b>.<br />
              Сотрудник: <b>staff</b>.<br />
              Пароль для всех: <b>demo</b>.
            </p>
            <button
              className="text-button"
              onClick={() => {
                setLogin("maria");
                setPassword("demo");
              }}
            >
              Войти от имени Марии
            </button>
          </details>
        </section>
      </div>
    </main>
  );
}
export function AddCompany({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: (c: Company) => void;
}) {
  const { config } = useSession();
  const [form, setForm] = useState({
      legal_form: "OOO",
      name: "",
      registration_number: "",
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null);
  const legal = config!.legal_forms.find(
    (f) => f.legal_form === form.legal_form,
  )!;
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const c = await api<Company>("/companies", "POST", form);
      onAdded(c);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Добавить бизнес" onClose={onClose}>
      <p className="muted">
        Используйте вымышленные сведения. Проверяется только формат реквизитов.
      </p>
      <form onSubmit={save}>
        <label className="field">
          Правовая форма
          <select
            value={form.legal_form}
            onChange={(e) => {
              setForm({ ...form, legal_form: e.target.value });
              setError(null);
            }}
          >
            {config!.legal_forms.map((f) => (
              <option key={f.legal_form} value={f.legal_form}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Название компании
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            maxLength={200}
            required
          />
          <FieldError error={error} name="name" />
        </label>
        <label className="field">
          {legal.registration_label}
          <input
            inputMode="numeric"
            pattern={`[0-9]{${legal.registration_length}}`}
            maxLength={legal.registration_length}
            value={form.registration_number}
            onChange={(e) =>
              setForm({
                ...form,
                registration_number: e.target.value.replace(/\D/g, ""),
              })
            }
            required
          />
          <small>{legal.registration_length} цифр</small>
          <FieldError error={error} name="registration_number" />
        </label>
        <ErrorBox error={error} />
        <div className="actions">
          <Button variant="secondary" type="button" onClick={onClose}>
            Отмена
          </Button>
          <Button busy={busy}>Добавить бизнес</Button>
        </div>
      </form>
    </Modal>
  );
}
export function Companies() {
  const { user } = useSession(),
    nav = useNavigate(),
    r = useResource<{ items: Company[] }>("/companies");
  const [selected, setSelected] = useState(
      Number(localStorage.getItem(`delo:company:${user!.id}`)) || 0,
    ),
    [adding, setAdding] = useState(false);
  const company =
    r.data?.items.find((c) => c.id === selected) ||
    (r.data?.items.length === 1 ? r.data.items[0] : null);
  return (
    <>
      <Heading
        center
        title={`${user!.first_name}, здравствуйте!`}
        description="Для какого бизнеса вы хотите оформить кредит?"
      />
      <section className="panel company-picker">
        {r.loading ? (
          <Busy />
        ) : r.error ? (
          <ErrorBox error={r.error} retry={r.refresh} />
        ) : (
          <>
            <fieldset className="business-options">
              <legend className="sr-only">Ваши компании</legend>
              {r.data!.items.map((c) => (
                <label
                  key={c.id}
                  className={`business-option ${company?.id === c.id ? "chosen" : ""}`}
                >
                  <span className="business-symbol">
                    <Building2 size={22} />
                  </span>
                  <span>
                    <strong>{c.name}</strong>
                    <small>
                      {c.registration_label} {c.registration_number}
                    </small>
                  </span>
                  <input
                    type="radio"
                    name="company"
                    checked={company?.id === c.id}
                    onChange={() => setSelected(c.id)}
                  />
                </label>
              ))}
            </fieldset>
            {!r.data!.items.length && (
              <div className="empty">
                <Building2 />
                <h2>Пока нет добавленных бизнесов</h2>
                <p>Добавьте компанию, чтобы перейти к заявке.</p>
              </div>
            )}
            <Button variant="text" onClick={() => setAdding(true)}>
              <Plus size={18} />
              Добавить новый бизнес
            </Button>
            <div className="picker-bottom">
              {company && (
                <p className="small muted">
                  Продолжить от имени «{company.name}»
                </p>
              )}
              <Button
                disabled={!company}
                onClick={() => {
                  localStorage.setItem(
                    `delo:company:${user!.id}`,
                    String(company!.id),
                  );
                  nav(`/companies/${company!.id}`);
                }}
              >
                Продолжить
                <ArrowRight size={18} />
              </Button>
            </div>
          </>
        )}
      </section>
      {adding && (
        <AddCompany
          onClose={() => setAdding(false)}
          onAdded={(c) => {
            setSelected(c.id);
            setAdding(false);
            r.refresh();
          }}
        />
      )}
    </>
  );
}
export function NewsDialog({
  id,
  onClose,
}: {
  id: number;
  onClose: () => void;
}) {
  const r = useResource<News>(`/news/${id}`);
  return (
    <Modal title={r.data?.title || "Материал для бизнеса"} onClose={onClose}>
      {r.loading ? (
        <Busy />
      ) : r.error ? (
        <ErrorBox error={r.error} retry={r.refresh} />
      ) : (
        <div className="article-body">
          {r.data?.body?.split("\n\n").map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
    </Modal>
  );
}
export function NewsList({ items }: { items: News[] }) {
  const [article, setArticle] = useState<number | null>(null);
  return (
    <>
      <div className="news-grid">
        {items.map((n) => (
          <button
            key={n.id}
            className="news-item"
            onClick={() => setArticle(n.id)}
          >
            <span className="news-tag">
              {
                (
                  {
                    GENERAL: "Разобраться в финансах",
                    IP: "Для предпринимателей",
                    OOO: "Для вашей компании",
                    WORKING_CAPITAL: "Оборотные средства",
                    EQUIPMENT: "Оборудование",
                  } as Record<string, string>
                )[n.tag]
              }
            </span>
            <strong>{n.title}</strong>
            <p>{n.summary}</p>
            <span className="news-open">
              Читать
              <ArrowUpRight size={16} />
            </span>
          </button>
        ))}
      </div>
      {article != null && (
        <NewsDialog id={article} onClose={() => setArticle(null)} />
      )}
    </>
  );
}
export function DashboardPage() {
  const { companyId } = useParams(),
    { user } = useSession(),
    r = useResource<Dashboard>(`/companies/${companyId}/dashboard`);
  const [ratingInfo, setRatingInfo] = useState(false);
  if (r.loading) return <Busy />;
  if (r.error) return <ErrorBox error={r.error} retry={r.refresh} />;
  const d = r.data!,
    current =
      d.active_applications.find((a) => a.status !== "DRAFT") ||
      d.active_applications[0];
  return (
    <>
      <header className="dashboard-hero">
        <p>Добрый день, {user!.first_name}</p>
        <h1>
          Бизнесу —<br />
          следующий шаг.
        </h1>
        <p>Финансирование, понятное на каждом этапе.</p>
      </header>
      <div className="dashboard-grid">
        <section className="panel current-application">
          {current ? (
            <>
              <div className="row">
                <h2>{current.number || "Ваша заявка"}</h2>
                <Badge app={current} />
              </div>
              <div className="display-amount">{money(current.amount)}</div>
              <p className="muted">
                {current.product_name ||
                  current.existing_loan_name ||
                  current.borrowing_mode_label}{" "}
                · {current.term_months} месяцев
              </p>
              {current.status !== "DRAFT" && (
                <CurrentTimeline id={current.id} />
              )}
              <div className="application-message">
                <span className="small muted">
                  {current.status === "DRAFT"
                    ? "Параметры уже сохранены. Продолжите, когда будет удобно."
                    : current.status === "NEED_INFO"
                      ? "Банк запросил уточнение. Ответьте в карточке заявки."
                      : "Актуальный статус и все действия — в карточке заявки."}
                </span>
                <Link className="link" to={applicationUrl(current)}>
                  {current.status === "DRAFT"
                    ? "Продолжить заполнение"
                    : "Открыть заявку"}
                  <ArrowUpRight size={16} />
                </Link>
              </div>
              {d.active_applications.length > 1 && (
                <div className="additional-apps">
                  {d.active_applications
                    .filter((a) => a.id !== current.id)
                    .map((a) => (
                      <ApplicationLink key={a.id} app={a} />
                    ))}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="empty-symbol">
                <Wallet size={30} />
              </div>
              <h2 className="empty-title">Место для ваших планов</h2>
              <p className="muted">
                Здесь появится ваша заявка.
                <br />
                Все этапы, условия и решения — в одном месте.
              </p>
              <div className="application-message">
                <p className="small muted">
                  Вы выбираете задачу.
                  <br />
                  Мы помогаем пройти остальные шаги.
                </p>
                <Link className="link" to={`/companies/${companyId}/new`}>
                  Подобрать финансирование
                  <ArrowUpRight size={16} />
                </Link>
              </div>
            </>
          )}
        </section>
        <section className="panel rating-panel">
          <div className="row">
            <h2>Рейтинг компании</h2>
            <button
              className="icon-button muted"
              aria-label="Что означает рейтинг"
              onClick={() => setRatingInfo(true)}
            >
              <HelpCircle size={18} />
            </button>
          </div>
          {d.rating ? (
            <>
              <div className="rating-number">
                {d.rating.score}
                <span> / {d.rating.max}</span>
              </div>
              <div
                className="rating-track"
                role="meter"
                aria-label="Демонстрационный рейтинг компании"
                aria-valuemin={0}
                aria-valuemax={d.rating.max}
                aria-valuenow={d.rating.score}
              >
                <span
                  style={{ width: `${(d.rating.score / d.rating.max) * 100}%` }}
                />
              </div>
              <p>
                {d.rating.band_label[0].toUpperCase() +
                  d.rating.band_label.slice(1)}{" "}
                рейтинг
              </p>
              <small className="muted">
                Демонстрационные данные бюро
                <br />
                Обновлено {date(d.rating.updated_at)}
              </small>
            </>
          ) : (
            <p className="muted">{d.rating_unavailable_text}</p>
          )}
        </section>
        <section className="panel next-panel">
          <h2>
            Планы есть.
            <br />
            Начнём?
          </h2>
          <p>Финансирование под задачу вашего бизнеса.</p>
          <Link className="button primary" to={`/companies/${companyId}/new`}>
            Взять новый кредит
            <Plus size={17} />
          </Link>
        </section>
      </div>
      <section className="panel loans-panel">
        <h2>Действующие кредиты</h2>
        {!d.loans.length ? (
          <p className="muted">Действующих кредитов нет.</p>
        ) : (
          d.loans.map((l) => (
            <div className="loan-item" key={l.id}>
              <div>
                <h3>{l.name}</h3>
                <p className="muted small">
                  Выдано {money(l.original_amount)} · {percent(l.rate)} годовых
                </p>
              </div>
              <div>
                <small className="muted">Остаток долга</small>
                <strong>{money(l.balance)}</strong>
              </div>
              <div>
                <small className="muted">
                  Платёж {date(l.next_payment_date)}
                </small>
                <strong>{money(l.next_payment_amount)}</strong>
              </div>
              <Link className="link" to={`/companies/${companyId}/new`}>
                Изменить условия
                <ArrowUpRight size={16} />
              </Link>
            </div>
          ))
        )}
      </section>
      {d.past_applications.length > 0 && (
        <section className="section">
          <div className="section-title">
            <h2>Прошлые обращения</h2>
            <Link className="link" to={`/companies/${companyId}/applications`}>
              Все заявки
              <ArrowUpRight size={16} />
            </Link>
          </div>
          <div className="panel app-list">
            {d.past_applications.slice(0, 3).map((a) => (
              <ApplicationLink key={a.id} app={a} />
            ))}
          </div>
        </section>
      )}
      <section className="section">
        <div className="section-title">
          <h2>Для вашего бизнеса</h2>
          <Link className="link" to={`/companies/${companyId}/news`}>
            Все материалы
            <ArrowUpRight size={16} />
          </Link>
        </div>
        <NewsList items={d.news.slice(0, 3)} />
      </section>
      {ratingInfo && (
        <Modal
          title="Что означает рейтинг"
          onClose={() => setRatingInfo(false)}
        >
          <p>
            {d.rating?.hint ||
              "Рейтинг временно недоступен. Предварительные условия рассчитываются без него."}
          </p>
          <p className="muted small">
            Источник — локальный симулятор. Реальная кредитная история не
            запрашивается.
          </p>
        </Modal>
      )}
    </>
  );
}
export function ModePage() {
  const { companyId } = useParams(),
    nav = useNavigate();
  const [busy, setBusy] = useState<Mode | null>(null),
    [error, setError] = useState<Error | null>(null);
  async function start(mode: Mode) {
    if (busy) return;
    setBusy(mode);
    setError(null);
    try {
      const a = await api<Application>(
        `/companies/${companyId}/applications`,
        "POST",
        { borrowing_mode: mode },
      );
      nav(applicationUrl(a));
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(null);
    }
  }
  return (
    <>
      <Heading
        center
        back={`/companies/${companyId}`}
        title="У каждого плана свой первый шаг."
        description="Выберите задачу. Мы проведём вас по остальным этапам."
      />
      <ErrorBox error={error} />
      <div className="mode-choices">
        <button
          disabled={!!busy}
          className="mode-choice"
          onClick={() => start("NEW_CREDIT")}
        >
          <Plus size={64} strokeWidth={1} />
          <h2>Новый кредит</h2>
          <p>
            Закупки, текущие расходы
            <br />
            или оборудование.
          </p>
          <span>
            {busy === "NEW_CREDIT" ? "Открываем заявку…" : "Выбрать"}
            <ArrowRight size={17} />
          </span>
        </button>
        <button
          disabled={!!busy}
          className="mode-choice refinance"
          onClick={() => start("REFINANCE")}
        >
          <RefreshCw size={58} strokeWidth={1} />
          <h2>Рефинансирование</h2>
          <p>
            Пересмотрите условия
            <br />
            действующего кредита.
          </p>
          <span>
            {busy === "REFINANCE" ? "Открываем заявку…" : "Рассчитать"}
            <ArrowRight size={17} />
          </span>
        </button>
      </div>
      {error instanceof ApiError && error.code === "NO_LOANS_TO_REFINANCE" && (
        <div className="center-action">
          <Button busy={!!busy} onClick={() => start("NEW_CREDIT")}>
            Оформить новый кредит
          </Button>
        </div>
      )}
    </>
  );
}
export function ApplicationsPage() {
  const { companyId } = useParams(),
    r = useResource<{ items: Brief[] }>(`/companies/${companyId}/applications`);
  return (
    <>
      <Heading
        title="Мои заявки"
        description="Текущие обращения, черновики и решения банка."
        back={`/companies/${companyId}`}
      >
        <Link className="button primary" to={`/companies/${companyId}/new`}>
          <Plus size={18} />
          Новая заявка
        </Link>
      </Heading>
      {r.loading ? (
        <Busy />
      ) : r.error ? (
        <ErrorBox error={r.error} retry={r.refresh} />
      ) : r.data?.items.length ? (
        <div className="panel app-list">
          {r.data.items.map((a) => (
            <ApplicationLink key={a.id} app={a} />
          ))}
        </div>
      ) : (
        <section className="panel empty">
          <Wallet size={32} />
          <h2>Здесь будут ваши заявки</h2>
          <p>Начните с выбора задачи для бизнеса.</p>
          <Link className="link" to={`/companies/${companyId}/new`}>
            Подобрать финансирование
            <ArrowRight size={16} />
          </Link>
        </section>
      )}
    </>
  );
}
export function NewsPage() {
  const { companyId } = useParams(),
    r = useResource<{ items: News[] }>(`/news?company_id=${companyId}`);
  return (
    <>
      <Heading
        title="Для вашего бизнеса"
        description="Коротко о решениях, которые помогают двигаться дальше."
        back={`/companies/${companyId}`}
      />
      {r.loading ? (
        <Busy />
      ) : r.error ? (
        <ErrorBox error={r.error} retry={r.refresh} />
      ) : (
        <NewsList items={r.data?.items || []} />
      )}
    </>
  );
}
export function Help() {
  const r = useResource<{
    items: { id: number; question: string; answer: string }[];
  }>("/support");
  return (
    <>
      <Heading
        title="Давайте разберёмся"
        description="Ответы на вопросы о демонстрационном кабинете."
      />
      <section className="panel help-panel">
        {r.loading ? (
          <Busy />
        ) : r.error ? (
          <ErrorBox error={r.error} retry={r.refresh} />
        ) : (
          r.data?.items.map((x) => (
            <details key={x.id}>
              <summary>
                {x.question}
                <ChevronDown size={18} />
              </summary>
              <p>{x.answer}</p>
            </details>
          ))
        )}
      </section>
    </>
  );
}

function CurrentTimeline({ id }: { id: number }) {
  const r = useResource<Application>(`/applications/${id}`);
  return r.data ? (
    <Progress app={r.data} />
  ) : r.error ? (
    <ErrorBox error={r.error} retry={r.refresh} />
  ) : null;
}
