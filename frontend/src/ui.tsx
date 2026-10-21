import {
  useEffect,
  useRef,
  type ReactNode,
  type ButtonHTMLAttributes,
} from "react";
import { ArrowLeft, ArrowUpRight, Check, LoaderCircle, X } from "lucide-react";
import { Link } from "react-router-dom";
import { ApiError, date, money, percent } from "./api";
import type { Application, Brief, Terms } from "./types";
export function Button({
  children,
  busy = false,
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  busy?: boolean;
  variant?: "primary" | "secondary" | "text" | "danger";
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || busy}
      className={`button ${variant} ${className}`}
      aria-busy={busy || undefined}
    >
      {busy && <LoaderCircle size={17} className="spin" />}
      {children}
    </button>
  );
}
export function Busy({ label = "Загружаем данные…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={24} className="spin" />
      <span>{label}</span>
    </div>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  return error ? (
    <div className="notice error" role="alert">
      <strong>{error.message}</strong>
      {error instanceof ApiError && Object.keys(error.fields).length > 0 && (
        <ul>
          {[...new Set(Object.values(error.fields))].map((v) => (
            <li key={v}>{v}</li>
          ))}
        </ul>
      )}
      {retry && (
        <Button variant="text" onClick={retry}>
          Попробовать снова
        </Button>
      )}
    </div>
  ) : null;
}
export function FieldError({
  error,
  name,
}: {
  error: Error | null;
  name: string;
}) {
  const text = error instanceof ApiError ? error.fields[name] : null;
  return text ? (
    <span className="field-error" id={`${name}-error`}>
      {text}
    </span>
  ) : null;
}
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    const previousFocus = document.activeElement;
    el?.showModal();
    return () => {
      el?.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus({ preventScroll: true });
      }
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      aria-labelledby="dialog-title"
    >
      <div className="modal-top">
        <h2 id="dialog-title">{title}</h2>
        <button className="icon-button" onClick={onClose} aria-label="Закрыть">
          <X size={21} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Heading({
  title,
  description,
  back,
  children,
  center = false,
}: {
  title: string;
  description?: string;
  back?: string;
  children?: ReactNode;
  center?: boolean;
}) {
  return (
    <header className={`page-heading ${center ? "center" : ""}`}>
      {back && (
        <Link className="back" to={back}>
          <ArrowLeft size={16} />
          Назад
        </Link>
      )}
      <div className="heading-row">
        <div>
          <h1 tabIndex={-1}>{title}</h1>
          {description && <p>{description}</p>}
        </div>
        {children}
      </div>
    </header>
  );
}
export function Badge({
  app,
}: {
  app: Pick<Brief, "status" | "status_label">;
}) {
  return (
    <span className={`badge status-${app.status.toLowerCase()}`}>
      <span />
      {app.status_label}
    </span>
  );
}
export const applicationUrl = (app: Brief) =>
  app.status === "DRAFT"
    ? `/applications/${app.id}/edit/${app.current_step || (app.borrowing_mode === "REFINANCE" ? "refinance_loan" : "parameters")}`
    : `/applications/${app.id}`;
export function ApplicationLink({ app }: { app: Brief }) {
  return (
    <Link className="application-row" to={applicationUrl(app)}>
      <div>
        <strong>{app.number || "Черновик заявки"}</strong>
        <p>
          {app.product_name ||
            app.existing_loan_name ||
            app.borrowing_mode_label}
        </p>
        <span className="muted small">
          {date(app.submitted_at || app.created_at)}
        </span>
      </div>
      <div className="row-end">
        <strong>{money(app.amount)}</strong>
        <Badge app={app} />
      </div>
      <ArrowUpRight className="row-arrow" size={19} />
    </Link>
  );
}
export function Progress({ app }: { app: Application }) {
  return (
    <ol className="progress" aria-label="Этапы рассмотрения">
      {app.stage.steps.map((s, i) => (
        <li
          key={s.key}
          className={s.state}
          aria-current={s.state === "active" ? "step" : undefined}
        >
          <span className="progress-point">
            {s.state === "done" ? <Check size={12} /> : null}
          </span>
          <strong>{s.label}</strong>
          <small>
            {s.state === "done"
              ? "Пройден"
              : s.state === "active"
                ? "Текущий этап"
                : "Ожидается"}
          </small>
          <span className="sr-only">
            {i + 1} из {app.stage.steps.length}
          </span>
        </li>
      ))}
    </ol>
  );
}
export function TermsView({ terms }: { terms: Partial<Terms> }) {
  return (
    <dl className="terms">
      <div>
        <dt>Сумма</dt>
        <dd>{money(terms.amount)}</dd>
      </div>
      <div>
        <dt>Срок</dt>
        <dd>{terms.term_months ?? "—"} мес.</dd>
      </div>
      <div>
        <dt>Ставка</dt>
        <dd>{percent(terms.rate)}</dd>
      </div>
      <div>
        <dt>Ежемесячный платёж</dt>
        <dd>{money(terms.monthly_payment)}</dd>
      </div>
    </dl>
  );
}
export function History({ app }: { app: Application }) {
  return (
    <section className="panel history" id="history">
      <h2>История заявки</h2>
      {!app.events.length ? (
        <p className="muted">История появится после отправки заявки.</p>
      ) : (
        <ol>
          {app.events.map((e) => (
            <li key={e.id}>
              <span className="history-dot" />
              <div>
                <strong>{e.label}</strong>
                <p className="muted small">
                  {e.actor} · {date(e.created_at, true)}
                </p>
                {e.text && <p className="pre-line">{e.text}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
