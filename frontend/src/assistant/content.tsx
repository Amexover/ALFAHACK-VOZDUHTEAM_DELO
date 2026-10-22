import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUpRight,
  BookOpen,
  Check,
  Copy,
  FileText,
  Search,
} from "lucide-react";
import { api, date, money, percent } from "../api";
import { Busy, Button, ErrorBox, Modal, TermsView } from "../ui";
import type { KnowledgeDocument, Source } from "./types";
import type { Rating, Terms } from "../types";

export function safeLink(url?: string | null) {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) &&
      !parsed.username &&
      !parsed.password
      ? parsed.href
      : undefined;
  } catch {
    return undefined;
  }
}

export function Markdown({
  text,
  sources = [],
  onSource,
}: {
  text: string;
  sources?: Source[];
  onSource?: (source: Source) => void;
}) {
  const cited = onSource
    ? text.replace(/\[([a-z0-9:_-]+)\](?!\()/gi, (original, id) => {
        const index = sources.findIndex((s) => s.id === id);
        return index >= 0
          ? `[${index + 1}](#assistant-source-${index})`
          : original;
      })
    : text;
  return (
    <div className="assistant-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const citation = href?.match(/^#assistant-source-(\d+)$/),
              item = citation ? sources[Number(citation[1])] : null;
            if (item && onSource)
              return (
                <button
                  className="assistant-citation"
                  title={item.title}
                  aria-label={`Источник: ${item.title}`}
                  onClick={() => onSource(item)}
                >
                  {children}
                </button>
              );
            return safeLink(href) ? (
              <a
                href={safeLink(href)}
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
                <ArrowUpRight size={12} />
              </a>
            ) : (
              <span>{children}</span>
            );
          },
          img: ({ alt }) => <span>{alt}</span>,
          table: ({ children }) => (
            <div
              className="assistant-table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Таблица в ответе"
            >
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {cited}
      </ReactMarkdown>
    </div>
  );
}

/** Built-in server documents contain structured facts; present their public labels. */
function readableDocument(doc: KnowledgeDocument) {
  try {
    if (doc.id === "products")
      return (JSON.parse(doc.body) as { name: string; description: string }[])
        .map((p) => `## ${p.name}\n\n${p.description}`)
        .join("\n\n");
    if (doc.id === "application-statuses")
      return Object.values(
        JSON.parse(doc.body) as Record<
          string,
          { label: string; next_step: string }
        >,
      )
        .map((s) => `### ${s.label}\n\n${s.next_step}`)
        .join("\n\n");
    if (doc.id === "support")
      return (JSON.parse(doc.body) as { question: string; answer: string }[])
        .map((q) => `### ${q.question}\n\n${q.answer}`)
        .join("\n\n");
    if (doc.id === "business-profile") {
      const end = doc.body.lastIndexOf("]") + 1;
      return (
        (
          JSON.parse(doc.body.slice(0, end)) as {
            label: string;
            hint: string;
          }[]
        )
          .map((f) => `### ${f.label}\n\n${f.hint}`)
          .join("\n\n") +
        "\n\n" +
        doc.body.slice(end).trim()
      );
    }
    if (doc.id === "pricing") {
      const end = doc.body.lastIndexOf("}") + 1,
        data = JSON.parse(doc.body.slice(0, end));
      return `## Сумма и срок\n\nМинимальная сумма: ${money(data.amount.min)}.\n\nМаксимум для ИП: ${money(data.amount.max_by_legal_form.IP)}, для ООО: ${money(data.amount.max_by_legal_form.OOO)}.\n\nСрок: от ${data.term.min} до ${data.term.max} месяцев.\n\n## Предварительная ставка\n\n${data.rating.bands.map((b: { from: number; to: number; label: string; base_rate: number }) => `- ${b.label} рейтинг (${b.from}–${b.to}): базовая ставка ${percent(b.base_rate)}.`).join("\n")}\n\n${doc.body.slice(end).trim()}`;
    }
  } catch {
    /* A changed server format remains readable as supplied text. */
  }
  return doc.body;
}

function preview(item: Source) {
  if (item.url?.startsWith("/api/assistant/knowledge/products"))
    return "На что можно направить оборотный кредит и кредит на оборудование, как устроены платежи.";
  if (item.url?.startsWith("/api/assistant/knowledge/pricing"))
    return "Допустимые суммы и сроки, связь рейтинга с предварительной ставкой. Актуальные параметры — внутри материала.";
  if (item.url?.startsWith("/api/assistant/knowledge/application-statuses"))
    return "Что означает текущий статус заявки и какой следующий шаг ожидается от клиента.";
  if (item.url?.startsWith("/api/assistant/knowledge/business-profile"))
    return "Какие сведения о бизнесе нужны для рассмотрения и как подготовить анкету.";
  if (item.url?.startsWith("/api/assistant/knowledge/support"))
    return "Ответы на частые вопросы о кабинете, рейтинге и рефинансировании.";
  return item.excerpt.slice(0, 230) + (item.excerpt.length > 230 ? "…" : "");
}

function BankSource({
  source,
  onClose,
}: {
  source: Source;
  onClose: () => void;
}) {
  const match = source.url?.match(
    /^\/api\/(companies|staff\/applications|applications)\/(\d+)(?:\/dashboard)?$/,
  );
  const route = match
    ? `/${match[1]}/${match[2]}`
    : source.id === "queue"
      ? "/staff"
      : null;
  let snapshot:
    (Partial<Terms> & { company?: { name: string }; rating?: Rating }) | null =
    null;
  try {
    snapshot = JSON.parse(source.excerpt);
  } catch {
    /* Source excerpts may be truncated by the API. */
  }
  return (
    <div className="assistant-bank-source">
      <p>
        Помощник использовал данные банковского сервиса в выбранном контексте.
        Сверьте важные выводы с актуальной карточкой.
      </p>
      {source.id === "rating" && snapshot?.rating && (
        <dl className="profile-review">
          <div>
            <dt>Компания</dt>
            <dd>{snapshot.company?.name || "Выбранная компания"}</dd>
          </div>
          <div>
            <dt>Рейтинг бюро</dt>
            <dd>
              {snapshot.rating.score} / {snapshot.rating.max}
            </dd>
          </div>
          <div>
            <dt>Уровень</dt>
            <dd>{snapshot.rating.band_label}</dd>
          </div>
          <div>
            <dt>Обновление рейтинга</dt>
            <dd>{date(snapshot.rating.updated_at)}</dd>
          </div>
        </dl>
      )}
      {source.id === "quote" && snapshot && (
        <>
          <TermsView terms={snapshot} />
          <p className="muted small">
            Предварительный расчёт. Итоговые условия определяет банк.
          </p>
        </>
      )}
      {source.id === "scoring" && (
        <p className="muted small">
          Внутренняя оценка заявки отличается от рейтинга бюро. Её основания и
          рекомендация доступны сотруднику в карточке заявки.
        </p>
      )}
      {route && (
        <Link className="button secondary" onClick={onClose} to={route}>
          Открыть актуальные данные
          <ArrowUpRight size={16} />
        </Link>
      )}
      {!route && source.id === "products" && (
        <Link className="button secondary" onClick={onClose} to="/help">
          Условия и справка
          <ArrowUpRight size={16} />
        </Link>
      )}
    </div>
  );
}

export function CopyButton({ text }: { text: string }) {
  const [status, setStatus] = useState<"idle" | "copied" | "error">("idle");
  useEffect(() => {
    if (status !== "idle") {
      const timer = window.setTimeout(() => setStatus("idle"), 2500);
      return () => clearTimeout(timer);
    }
  }, [status]);
  return (
    <button
      className="assistant-copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setStatus("copied");
        } catch {
          setStatus("error");
        }
      }}
    >
      <span aria-live="polite">
        {status === "copied" ? <Check size={14} /> : <Copy size={14} />}
      </span>
      {status === "copied"
        ? "Скопировано"
        : status === "error"
          ? "Выделите и скопируйте текст"
          : "Копировать"}
    </button>
  );
}

export function SourceViewer({
  source,
  onClose,
}: {
  source: Source;
  onClose: () => void;
}) {
  const [document, setDocument] = useState<KnowledgeDocument | null>(null),
    [error, setError] = useState<Error | null>(null);
  const internal = source.url?.match(
    /^\/api\/assistant\/knowledge\/([a-z][a-z0-9-]*)$/,
  );
  useEffect(() => {
    if (!internal) return;
    const ctrl = new AbortController();
    api<KnowledgeDocument>(
      `/assistant/knowledge/${internal[1]}`,
      "GET",
      undefined,
      ctrl.signal,
    )
      .then(setDocument)
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e);
      });
    return () => ctrl.abort();
  }, [source.id]);
  return (
    <Modal title={source.title} onClose={onClose}>
      <p className="assistant-document-meta">
        {source.kind === "bank_data"
          ? "Данные выбранного контекста"
          : source.kind === "news"
            ? "Материал для бизнеса"
            : "База знаний"}
        {source.published_at
          ? ` · ${source.kind === "bank_data" ? "Прочитаны " : ""}${date(source.published_at, source.kind === "bank_data")}`
          : ""}
        {source.is_demo ? " · Демонстрационный материал" : ""}
      </p>
      {source.kind === "bank_data" ? (
        <BankSource source={source} onClose={onClose} />
      ) : internal && !document && !error ? (
        <Busy label="Открываем материал…" />
      ) : (
        <Markdown
          text={
            document
              ? readableDocument(document)
              : source.excerpt || "Текст источника доступен по ссылке ниже."
          }
        />
      )}
      <ErrorBox error={error} />
      {safeLink(source.url) && (
        <a
          className="button secondary"
          href={safeLink(source.url)}
          target="_blank"
          rel="noopener noreferrer"
        >
          Открыть источник
          <ArrowUpRight size={16} />
        </a>
      )}
    </Modal>
  );
}

export function Sources({
  items,
  onOpen,
}: {
  items: Source[];
  onOpen: (s: Source) => void;
}) {
  if (!items.length) return null;
  return (
    <details className="assistant-sources">
      <summary>
        <BookOpen size={14} />
        Материалы для ответа <span>{items.length}</span>
      </summary>
      <p>
        Переданы помощнику для подготовки ответа. Сверьте важные выводы с
        источниками.
      </p>
      <div>
        {items.map((s) => (
          <button key={s.id} onClick={() => onOpen(s)}>
            <FileText size={15} />
            <span>
              {s.title}
              {s.is_demo && <small>Демонстрационный материал</small>}
            </span>
            <ArrowUpRight size={14} />
          </button>
        ))}
      </div>
    </details>
  );
}

const TOPICS = [
  "Кредитный рейтинг",
  "Подготовка заявки",
  "Рефинансирование",
  "Статусы заявки",
];
export function Library({
  kind,
  onAsk,
  onOpen,
}: {
  kind: "knowledge" | "news";
  onAsk: (text: string) => void;
  onOpen: (s: Source) => void;
}) {
  const [query, setQuery] = useState(
      kind === "knowledge" ? "Кредитный рейтинг" : "",
    ),
    [submitted, setSubmitted] = useState(query);
  const [items, setItems] = useState<Source[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState<Error | null>(null),
    [version, setVersion] = useState(0);
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    setItems([]);
    api<{ items: Source[] }>(
      `/assistant/${kind}?q=${encodeURIComponent(submitted)}`,
      "GET",
      undefined,
      ctrl.signal,
    )
      .then((d) => setItems(d.items))
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [kind, submitted, version]);
  return (
    <section className="assistant-library">
      <header>
        <h2>
          {kind === "news"
            ? "В фокусе бизнеса"
            : "Ответ начинается с источника"}
        </h2>
        <p>
          {kind === "news"
            ? "Публикации, отобранные редактором. У каждого материала — свой контекст."
            : "Правила продуктов, этапы рассмотрения и ответы на частые вопросы."}
        </p>
      </header>
      <form
        className="assistant-search"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query.trim());
          setVersion((v) => v + 1);
        }}
      >
        <Search size={18} />
        <input
          aria-label="Поиск материалов"
          value={query}
          maxLength={300}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Что хотите найти?"
          required={kind === "knowledge"}
        />
        <button type="submit">Найти</button>
      </form>
      {kind === "knowledge" && (
        <div className="assistant-topics">
          {TOPICS.map((t) => (
            <button
              key={t}
              aria-pressed={submitted === t}
              onClick={() => {
                setQuery(t);
                setSubmitted(t);
              }}
            >
              {t}
            </button>
          ))}
        </div>
      )}
      <ErrorBox error={error} retry={() => setVersion((v) => v + 1)} />
      {loading ? (
        <Busy label="Ищем материалы…" />
      ) : !error && !items.length ? (
        <div className="assistant-empty">
          <BookOpen size={28} />
          <h3>Пока ничего не нашлось</h3>
          <p>
            Попробуйте другую формулировку, например «кредит» или «рейтинг».
          </p>
        </div>
      ) : (
        <div className="assistant-reading-list">
          {items.map((item) => (
            <article key={item.id}>
              <div className="assistant-document-meta">
                {item.is_demo
                  ? "Демонстрационный материал"
                  : kind === "news"
                    ? "Публикация редакции"
                    : "База знаний"}
                {item.published_at && ` · ${date(item.published_at)}`}
              </div>
              <button
                className="assistant-article-title"
                onClick={() => onOpen(item)}
              >
                {item.title}
                <ArrowUpRight size={19} />
              </button>
              <p>{preview(item)}</p>
              <button
                className="text-button"
                onClick={() =>
                  onAsk(
                    `Объясни простыми словами материал «${item.title}». Используй доступную базу знаний и укажи источники.`,
                  )
                }
              >
                Обсудить с помощником
                <ArrowUpRight size={14} />
              </button>
            </article>
          ))}
        </div>
      )}
      {kind === "news" && (
        <p className="assistant-library-note">
          Материалы без даты помечены как демонстрационные. Автоматическая
          новостная лента не подключена.
        </p>
      )}
    </section>
  );
}

export function Editor({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [slug, setSlug] = useState(""),
    [title, setTitle] = useState(""),
    [body, setBody] = useState(""),
    [audience, setAudience] = useState("client"),
    [kind, setKind] = useState("knowledge"),
    [url, setUrl] = useState(""),
    [published, setPublished] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<Error | null>(null),
    [loaded, setLoaded] = useState(false);
  async function load() {
    setBusy(true);
    setError(null);
    try {
      const doc = await api<KnowledgeDocument>(`/assistant/knowledge/${slug}`);
      setTitle(doc.title);
      setBody(doc.body);
      setAudience(doc.audience);
      setKind(doc.kind);
      setUrl(safeLink(doc.url) || "");
      setPublished(
        doc.published_at
          ? new Date(
              new Date(doc.published_at).getTime() -
                new Date().getTimezoneOffset() * 60000,
            )
              .toISOString()
              .slice(0, 16)
          : "",
      );
      setLoaded(true);
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Публикация материала" onClose={onClose}>
      <p className="muted small">
        Материал станет доступен помощнику. Проверьте содержание и источник
        перед публикацией. Права на изменение проверяет сервер.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api(`/assistant/knowledge/${slug}`, "PUT", {
              title,
              body,
              audience,
              kind,
              source_url: url || null,
              published_at: published
                ? new Date(published).toISOString()
                : null,
            });
            onSaved();
            onClose();
          } catch (e) {
            setError(e as Error);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          Идентификатор
          <input
            pattern="[a-z][a-z0-9-]{0,79}"
            value={slug}
            onChange={(e) => {
              setSlug(e.target.value);
              setLoaded(false);
            }}
            required
            maxLength={80}
            placeholder="business-guide"
          />
          <small>
            Латинские буквы, цифры и дефисы. Существующий идентификатор обновит
            материал.
          </small>
        </label>
        <Button
          type="button"
          variant="text"
          busy={busy}
          disabled={!/^[a-z][a-z0-9-]{0,79}$/.test(slug)}
          onClick={load}
        >
          Загрузить существующий материал
        </Button>
        {loaded && (
          <p className="small muted">Материал загружен для редактирования.</p>
        )}
        <label className="field">
          Название
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            required
          />
        </label>
        <div className="assistant-editor-row">
          <label className="field">
            Тип
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="knowledge">База знаний</option>
              <option value="news">Новость</option>
            </select>
          </label>
          <label className="field">
            Кому доступен
            <select
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
            >
              <option value="client">Клиентам и сотрудникам</option>
              <option value="staff">Только сотрудникам</option>
            </select>
          </label>
        </div>
        <label className="field">
          Текст
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
            maxLength={40000}
            rows={7}
          />
        </label>
        <label className="field">
          Ссылка на источник
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required={kind === "news"}
            placeholder="https://…"
          />
        </label>
        <label className="field">
          Дата публикации
          <input
            type="datetime-local"
            value={published}
            onChange={(e) => setPublished(e.target.value)}
            required={kind === "news"}
          />
          <small>
            Для новости обязательны источник и прошедшая дата. Часовой пояс —
            вашего устройства.
          </small>
        </label>
        <ErrorBox error={error} />
        <div className="actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" busy={busy}>
            Опубликовать
          </Button>
        </div>
      </form>
    </Modal>
  );
}
