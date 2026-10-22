import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Building2,
  Check,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  FileText,
  History,
  Info,
  MessageSquare,
  Newspaper,
  PanelLeftClose,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  Trash2,
  TrendingUp,
  X,
} from "lucide-react";
import { api, ApiError, date, money } from "../api";
import { useSession } from "../context";
import { Badge, Busy, Button, ErrorBox, Modal } from "../ui";
import { AgentState, type AgentStatus } from "@/components/ui/agent-state";
import type { Application, Dashboard } from "../types";
import {
  CopyButton,
  Editor,
  Library,
  Markdown,
  Sources,
  SourceViewer,
} from "./content";
import { streamMessage } from "./stream";
import { newRequestId } from "./id";
import type {
  AssistantConfig,
  Conversation,
  Intent,
  Page,
  Source,
  StreamEvent,
  Turn,
} from "./types";
import { assistantUrl } from "./entry";
import "./styles.css";

type Tab = "chat" | "knowledge" | "news";
const INTENTS: Record<Intent, string> = {
  chat: "Вопрос помощнику",
  rating: "Разобрать рейтинг",
  advice: "Подготовить заявку",
  news: "Материалы для бизнеса",
  application_review: "Разобрать заявку",
  draft_reply: "Черновик ответа",
};
const TOOLS: Record<string, string> = {
  search_knowledge: "Ищу в базе знаний",
  get_news: "Подбираю материалы",
  get_company: "Смотрю данные компании",
  get_application: "Изучаю заявку",
  calculate_quote: "Рассчитываю условия",
  get_queue: "Изучаю очередь заявок",
};
const CLIENT_STARTERS: {
  intent: Intent;
  title: string;
  text: string;
  icon: typeof TrendingUp;
}[] = [
  {
    intent: "rating",
    title: "Что с моим рейтингом?",
    text: "Разбери кредитный рейтинг выбранной компании. Что он означает и какие выводы из него можно сделать? Не придумывай причины изменения балла.",
    icon: TrendingUp,
  },
  {
    intent: "advice",
    title: "Как подготовиться к кредиту?",
    text: "Помоги подготовить заявку на кредит для выбранной компании. Какие сведения стоит проверить и что понадобится?",
    icon: ClipboardList,
  },
  {
    intent: "chat",
    title: "Объясни условия и этапы",
    text: "Объясни простыми словами, как проходит рассмотрение заявки и чем предварительные условия отличаются от решения банка.",
    icon: CircleHelp,
  },
  {
    intent: "news",
    title: "Что почитать для бизнеса?",
    text: "Подбери доступные материалы для бизнеса и кратко объясни, чем они полезны. Укажи источники и отметь демонстрационные публикации.",
    icon: Newspaper,
  },
];
const STAFF_STARTERS: typeof CLIENT_STARTERS = [
  {
    intent: "application_review",
    title: "Собери сводку заявки",
    text: "Подготовь краткую сводку выбранной заявки: запрос клиента, анкета, проверки и текущая оценка. Отдельно укажи факты, риски и недостающие сведения.",
    icon: ClipboardList,
  },
  {
    intent: "application_review",
    title: "Каких сведений не хватает?",
    text: "Проверь полноту выбранной заявки. Какие противоречия и недостающие сведения требуют внимания сотрудника? Не принимай решение за банк.",
    icon: Search,
  },
  {
    intent: "draft_reply",
    title: "Подготовь ответ клиенту",
    text: "Составь вежливый черновик ответа клиенту по выбранной заявке с учётом её текущего статуса. Не обещай одобрение и не добавляй неподтверждённые условия.",
    icon: FileText,
  },
  {
    intent: "chat",
    title: "Помоги с очередью заявок",
    text: "Покажи краткую сводку доступной очереди заявок: статусы и обращения, которые требуют внимания. Не принимай решения и не меняй заявки.",
    icon: History,
  },
];

/** Each URL/context owns its state and aborts its stream when the user leaves. */
export function AssistantPage() {
  const [params] = useSearchParams(),
    { user } = useSession();
  return (
    <AssistantWorkspace
      key={`${user!.id}:${params.toString()}`}
      params={params}
    />
  );
}

function AssistantWorkspace({ params }: { params: URLSearchParams }) {
  const { user } = useSession(),
    staff = user!.role === "EMPLOYEE";
  const [, setParams] = useSearchParams();
  const initialId = params.get("conversation");
  const positive = (v: string | null) =>
    v && /^[1-9]\d*$/.test(v) && Number.isSafeInteger(Number(v))
      ? Number(v)
      : null;
  const [conversation, setConversation] = useState<Conversation | null>(null),
    [config, setConfig] = useState<AssistantConfig | null>(null),
    [configError, setConfigError] = useState<Error | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]),
    [hasOlder, setHasOlder] = useState(false),
    [loading, setLoading] = useState(!!initialId),
    [loadError, setLoadError] = useState<Error | null>(null);
  const [chats, setChats] = useState<Conversation[]>([]),
    [hasMoreChats, setHasMoreChats] = useState(false),
    [chatsLoading, setChatsLoading] = useState(true),
    [chatsError, setChatsError] = useState<Error | null>(null),
    [historyQuery, setHistoryQuery] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null),
    [application, setApplication] = useState<Application | null>(null),
    [contextError, setContextError] = useState<Error | null>(null),
    [contextLoading, setContextLoading] = useState(false),
    [contextVersion, setContextVersion] = useState(0);
  const [text, setText] = useState(""),
    [intent, setIntent] = useState<Intent>(
      Object.hasOwn(INTENTS, params.get("intent") || "")
        ? (params.get("intent") as Intent)
        : "chat",
    );
  const [busy, setBusy] = useState(false),
    [status, setStatus] = useState<AgentStatus>("idle"),
    [statusText, setStatusText] = useState(""),
    [stream, setStream] = useState(""),
    [question, setQuestion] = useState(""),
    [liveSources, setLiveSources] = useState<Source[]>([]),
    [sendError, setSendError] = useState<Error | null>(null);
  const [tab, setTab] = useState<Tab>("chat"),
    [sidebar, setSidebar] = useState(false),
    [contextOpen, setContextOpen] = useState(false),
    [source, setSource] = useState<Source | null>(null),
    [deleting, setDeleting] = useState<Conversation | null>(null),
    [deleteBusy, setDeleteBusy] = useState(false),
    [deleteError, setDeleteError] = useState<Error | null>(null),
    [editor, setEditor] = useState(false),
    [libraryVersion, setLibraryVersion] = useState(0),
    [awayFromBottom, setAwayFromBottom] = useState(false),
    [checking, setChecking] = useState(false);
  const controller = useRef<AbortController | null>(null),
    mounted = useRef(true),
    sending = useRef(false),
    textarea = useRef<HTMLTextAreaElement>(null),
    transcript = useRef<HTMLDivElement>(null),
    bottom = useRef<HTMLDivElement>(null),
    autoScroll = useRef(true);
  const attempt = useRef<{
    request_id: string;
    content: string;
    intent: Intent;
  } | null>(null);
  const companyId = conversation?.company_id ?? positive(params.get("company"));
  const applicationId =
    conversation?.application_id ?? positive(params.get("application"));
  const scopeReady = !loading && !loadError && (!initialId || !!conversation);
  const blocked =
    !config?.enabled ||
    !!configError ||
    !scopeReady ||
    !!contextError ||
    contextLoading;
  const [now, setNow] = useState(Date.now());
  const hasPending = turns.some(
    (t) =>
      t.status === "pending" &&
      now - new Date(t.created_at).getTime() < 220_000,
  );
  const starters = staff ? STAFF_STARTERS : CLIENT_STARTERS;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (!turns.some((t) => t.status === "pending")) return;
    const timer = window.setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, [turns]);
  useEffect(() => {
    if (config && !config.intents.includes(intent)) setIntent("chat");
  }, [config, intent]);

  const loadConfig = useCallback(async (signal?: AbortSignal) => {
    setConfigError(null);
    try {
      const result = await api<AssistantConfig>(
        "/assistant/config",
        "GET",
        undefined,
        signal,
      );
      if (!signal?.aborted && mounted.current) setConfig(result);
    } catch (e) {
      if (!signal?.aborted && mounted.current) setConfigError(e as Error);
    }
  }, []);
  useEffect(() => {
    const ctrl = new AbortController();
    void loadConfig(ctrl.signal);
    return () => ctrl.abort();
  }, [loadConfig]);

  const loadChats = useCallback(async (offset = 0, signal?: AbortSignal) => {
    setChatsLoading(true);
    setChatsError(null);
    try {
      const result = await api<Page<Conversation>>(
        `/assistant/conversations?limit=20&offset=${offset}`,
        "GET",
        undefined,
        signal,
      );
      if (mounted.current && !signal?.aborted) {
        setChats((prev) =>
          offset
            ? [
                ...prev,
                ...result.items.filter((c) => !prev.some((p) => p.id === c.id)),
              ]
            : result.items,
        );
        setHasMoreChats(result.has_more);
      }
    } catch (e) {
      if (mounted.current && !signal?.aborted) setChatsError(e as Error);
    } finally {
      if (mounted.current && !signal?.aborted) setChatsLoading(false);
    }
  }, []);
  useEffect(() => {
    const ctrl = new AbortController();
    void loadChats(0, ctrl.signal);
    return () => ctrl.abort();
  }, [loadChats]);

  const loadTurns = useCallback(
    async (id: string, offset = 0, signal?: AbortSignal) => {
      const result = await api<Page<Turn>>(
        `/assistant/conversations/${id}/messages?limit=30&offset=${offset}`,
        "GET",
        undefined,
        signal,
      );
      if (mounted.current && !signal?.aborted) {
        setTurns((prev) =>
          offset
            ? [
                ...result.items.filter((t) => !prev.some((p) => p.id === t.id)),
                ...prev,
              ]
            : result.items,
        );
        setHasOlder(result.has_more);
      }
      return result.items;
    },
    [],
  );

  useEffect(() => {
    if (!initialId) return;
    const ctrl = new AbortController();
    setLoading(true);
    setLoadError(null);
    api<Conversation>(
      `/assistant/conversations/${encodeURIComponent(initialId)}`,
      "GET",
      undefined,
      ctrl.signal,
    )
      .then(async (c) => {
        if (ctrl.signal.aborted) return;
        setConversation(c);
        await loadTurns(c.id, 0, ctrl.signal);
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) setLoadError(e);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [initialId, loadTurns]);

  useEffect(() => {
    if (!scopeReady) return;
    const ctrl = new AbortController();
    setDashboard(null);
    setApplication(null);
    setContextError(null);
    setContextLoading(true);
    (async () => {
      try {
        let cid = companyId;
        if (applicationId) {
          const a = await api<Application>(
            `/${staff ? "staff/" : ""}applications/${applicationId}`,
            "GET",
            undefined,
            ctrl.signal,
          );
          if (ctrl.signal.aborted) return;
          setApplication(a);
          cid = a.company_id;
        }
        if (!staff && cid) {
          const d = await api<Dashboard>(
            `/companies/${cid}/dashboard`,
            "GET",
            undefined,
            ctrl.signal,
          );
          if (!ctrl.signal.aborted) setDashboard(d);
        }
      } catch (e) {
        if (!ctrl.signal.aborted) setContextError(e as Error);
      } finally {
        if (!ctrl.signal.aborted) setContextLoading(false);
      }
    })();
    return () => ctrl.abort();
  }, [companyId, applicationId, scopeReady, staff, contextVersion]);

  useEffect(() => {
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 160)}px`;
    }
  }, [text, tab]);
  useEffect(() => {
    if (autoScroll.current && tab === "chat" && (turns.length || busy))
      bottom.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [stream, turns, busy, tab]);
  useEffect(() => {
    document.title = "Помощник — Дело";
  }, []);
  useEffect(() => {
    if (!sidebar) return;
    const previous = document.activeElement;
    const panel = document.querySelector<HTMLElement>(
      ".assistant-sidebar.is-open",
    );
    const focusable = () =>
      Array.from(
        panel?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input:not(:disabled), a[href]",
        ) || [],
      ).filter((e) => e.getClientRects().length);
    focusable()[0]?.focus();
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSidebar(false);
      if (event.key === "Tab") {
        const items = focusable(),
          first = items[0],
          last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keys);
    return () => {
      document.removeEventListener("keydown", keys);
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, [sidebar]);

  function startNew() {
    const q = new URLSearchParams();
    if (companyId && !staff) q.set("company", String(companyId));
    if (applicationId) q.set("application", String(applicationId));
    // Force a clean workspace even if the URL already describes a new conversation.
    q.set("new", newRequestId());
    setParams(q);
    setSidebar(false);
  }
  function openChat(c: Conversation) {
    setParams({ conversation: c.id });
    setSidebar(false);
  }
  function prepare(content: string, selected: Intent) {
    setTab("chat");
    setIntent(selected);
    setText(content);
    setSendError(null);
    window.setTimeout(() => textarea.current?.focus(), 0);
  }

  async function send(e?: FormEvent, retry = false) {
    e?.preventDefault();
    if (sending.current || blocked || hasPending) return;
    const content = text.trim();
    if (
      !content ||
      content.length > Math.min(config?.max_message_characters || 6000, 6000)
    )
      return;
    sending.current = true;
    setBusy(true);
    setSendError(null);
    setStream("");
    setQuestion(content);
    setLiveSources([]);
    setStatus("thinking");
    setStatusText("Собираю контекст для ответа");
    autoScroll.current = true;
    setAwayFromBottom(false);
    const ctrl = new AbortController();
    controller.current = ctrl;
    let current = conversation;
    const body =
      retry &&
      attempt.current?.content === content &&
      attempt.current.intent === intent
        ? attempt.current
        : { request_id: newRequestId(), content, intent };
    attempt.current = body;
    try {
      if (!current) {
        current = await api<Conversation>(
          "/assistant/conversations",
          "POST",
          {
            company_id: staff ? null : companyId,
            application_id: applicationId,
            title: content.slice(0, 100),
          },
          ctrl.signal,
        );
        if (!mounted.current || ctrl.signal.aborted) return;
        setConversation(current);
        void loadChats();
      }
      setText("");
      const cid = current.id;
      await streamMessage(cid, body, ctrl.signal, (event: StreamEvent) => {
        if (!mounted.current) return;
        if (event.type === "start") {
          setStatus("thinking");
        }
        if (event.type === "delta") {
          setStatus("working");
          setStatusText("Формулирую ответ");
          setStream((s) => s + event.text);
        }
        if (event.type === "tool") {
          setStatus("working");
          setStatusText(
            event.ok
              ? TOOLS[event.name] || "Проверяю данные"
              : "Источник временно недоступен",
          );
        }
        if (event.type === "sources") setLiveSources(event.items);
        if (event.type === "done") {
          setTurns((prev) => [
            ...prev.filter((t) => t.request_id !== event.turn.request_id),
            event.turn,
          ]);
          setStatus("complete");
          setStatusText("Ответ готов");
          setStream("");
          setQuestion("");
          attempt.current = null;
          void loadChats();
        }
      });
      if (mounted.current && !initialId)
        setParams({ conversation: cid }, { replace: true });
    } catch (e) {
      if (!mounted.current) return;
      setStream("");
      setLiveSources([]);
      setStatus(ctrl.signal.aborted ? "needs-input" : "error");
      setStatusText(
        ctrl.signal.aborted ? "Ответ остановлен" : "Не удалось завершить ответ",
      );
      const err = ctrl.signal.aborted
        ? new Error(
            "Ответ остановлен. Вопрос можно изменить и отправить заново.",
          )
        : (e as Error);
      setSendError(err);
      setText((prev) => prev || content);
      // A lost connection may hide a successfully persisted response. Reconcile first.
      if (current) {
        try {
          let result = await loadTurns(current.id);
          let saved = result.find((t) => t.request_id === body.request_id);
          // Disconnect cancellation and the DB commit can finish a moment apart.
          for (
            let n = 0;
            saved?.status === "pending" && n < 4 && mounted.current;
            n++
          ) {
            await new Promise((resolve) => window.setTimeout(resolve, 350));
            if (!mounted.current) break;
            result = await loadTurns(current.id);
            saved = result.find((t) => t.request_id === body.request_id);
          }
          if (saved?.status === "completed") {
            setSendError(null);
            setStatus("complete");
            setText("");
            attempt.current = null;
          } else if (saved?.status === "failed") attempt.current = null;
        } catch {
          /* Keep request_id to replay an uncertain result safely. */
        }
      }
    } finally {
      sending.current = false;
      if (mounted.current) {
        setBusy(false);
        setQuestion("");
        controller.current = null;
        textarea.current?.focus();
      }
    }
  }

  async function refreshHistory(older = false) {
    if (!conversation) return;
    setChecking(true);
    setLoadError(null);
    const before = transcript.current?.scrollHeight || 0;
    try {
      await loadTurns(conversation.id, older ? turns.length : 0);
      if (older) {
        autoScroll.current = false;
        requestAnimationFrame(() => {
          if (transcript.current)
            transcript.current.scrollTop +=
              transcript.current.scrollHeight - before;
        });
      }
    } catch (e) {
      setLoadError(e as Error);
    } finally {
      if (mounted.current) setChecking(false);
    }
  }

  const company = dashboard?.company || application?.company,
    rating = dashboard?.rating || application?.rating;
  const visibleChats = chats.filter((c) =>
    c.title
      .toLocaleLowerCase("ru")
      .includes(historyQuery.toLocaleLowerCase("ru")),
  );
  const empty = !turns.length && !busy;
  const activeStatus = !config?.enabled && config ? "needs-input" : status;
  return (
    <div className="assistant-page">
      <header className="assistant-page-heading">
        <div>
          <h1>
            Ваш помощник<span>.</span>
          </h1>
          <p>
            {staff
              ? "Больше ясности в каждой заявке."
              : "От первого вопроса до понятного следующего шага."}
          </p>
        </div>
        <span className="assistant-mode">
          <ShieldCheck size={15} />
          {staff ? "Кабинет сотрудника" : "Для вашего бизнеса"}
        </span>
      </header>
      <div className="assistant-shell">
        {sidebar && (
          <button
            className="assistant-sidebar-backdrop"
            aria-label="Скрыть историю"
            onClick={() => setSidebar(false)}
          />
        )}
        <aside
          className={`assistant-sidebar ${sidebar ? "is-open" : ""}`}
          role={sidebar ? "dialog" : undefined}
          aria-modal={sidebar || undefined}
          aria-label="История диалогов"
        >
          <div className="assistant-sidebar-heading">
            <span>Пространство диалога</span>
            <button
              className="icon-button assistant-mobile-only"
              aria-label="Закрыть историю"
              onClick={() => setSidebar(false)}
            >
              <PanelLeftClose size={18} />
            </button>
          </div>
          <button className="assistant-new" onClick={startNew}>
            <Plus size={18} />
            Новый диалог<kbd>+</kbd>
          </button>
          <label className="assistant-history-search">
            <Search size={14} />
            <input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder="Найти диалог"
              aria-label="Поиск в загруженной истории"
              maxLength={120}
            />
          </label>
          <div className="assistant-history-label">
            <span>Ваша история</span>
            <History size={13} />
          </div>
          <div className="assistant-history-list">
            {chatsError && (
              <div className="assistant-sidebar-error">
                <p>{chatsError.message}</p>
                <button onClick={() => void loadChats()}>Повторить</button>
              </div>
            )}
            {!chatsLoading && !chatsError && !visibleChats.length && (
              <p className="assistant-history-empty">
                {historyQuery
                  ? "Диалогов с таким названием нет."
                  : "Здесь появятся ваши разговоры с помощником."}
              </p>
            )}
            {visibleChats.map((c) => (
              <div
                className={`assistant-history-item ${conversation?.id === c.id ? "selected" : ""}`}
                key={c.id}
              >
                <button
                  onClick={() => openChat(c)}
                  aria-current={conversation?.id === c.id ? "page" : undefined}
                >
                  <MessageSquare size={15} />
                  <span>
                    {c.title}
                    <small>
                      {c.application_id
                        ? `Заявка · ${date(c.updated_at)}`
                        : c.company_id
                          ? `Компания · ${date(c.updated_at)}`
                          : date(c.updated_at)}
                    </small>
                  </span>
                </button>
                <button
                  className="assistant-delete-chat"
                  aria-label={`Удалить диалог «${c.title}»`}
                  onClick={() => {
                    setDeleting(c);
                    setDeleteError(null);
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {chatsLoading && (
              <p className="assistant-history-empty" role="status">
                Загружаем историю…
              </p>
            )}
            {hasMoreChats && (
              <button
                className="assistant-load-more"
                disabled={chatsLoading}
                onClick={() => void loadChats(chats.length)}
              >
                Показать ещё
              </button>
            )}
          </div>
          <div className="assistant-sidebar-bottom">
            <ShieldCheck size={19} />
            <div>
              <strong>Всё в вашем кабинете</strong>
              <p>Личная история. Доступ только к вашим данным.</p>
            </div>
          </div>
        </aside>
        <section className="assistant-stage" aria-label="Помощник">
          <div className="assistant-toolbar">
            <div className="assistant-toolbar-start">
              <button
                className="icon-button assistant-mobile-only"
                onClick={() => setSidebar(true)}
                aria-label="Открыть историю"
                aria-expanded={sidebar}
              >
                <History size={19} />
              </button>
              <span
                className={`assistant-presence ${config?.enabled ? "on" : ""}`}
              />
              <span>
                {config?.enabled
                  ? "Помощник"
                  : config
                    ? "Ожидает подключения"
                    : "Подключение…"}
              </span>
            </div>
            <div
              className="assistant-tabs"
              role="group"
              aria-label="Раздел помощника"
            >
              {(
                [
                  ["chat", MessageSquare, "Диалог"],
                  ["knowledge", BookOpen, "База знаний"],
                  ["news", Newspaper, "Материалы"],
                ] as const
              ).map(([key, Icon, label]) => (
                <button
                  key={key}
                  aria-pressed={tab === key}
                  onClick={() => setTab(key)}
                >
                  <Icon size={15} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
            <button
              className="icon-button assistant-context-toggle"
              aria-label="Контекст диалога"
              aria-expanded={contextOpen}
              onClick={() => setContextOpen((v) => !v)}
            >
              <SlidersHorizontal size={18} />
            </button>
          </div>
          {configError && (
            <div className="assistant-inline-notice">
              <ErrorBox
                error={
                  new Error(
                    configError instanceof ApiError &&
                      configError.status === 404
                      ? "API помощника пока недоступен на этом сервере. Подключите обновлённый бэкенд."
                      : configError.message,
                  )
                }
                retry={() => void loadConfig()}
              />
            </div>
          )}
          {config && !config.enabled && (
            <div className="assistant-offline">
              <Info size={16} />
              <p>
                <strong>Помощник ещё не подключён.</strong> Пока можно изучить
                базу знаний и материалы.
              </p>
              <button
                onClick={() => void loadConfig()}
                aria-label="Проверить подключение помощника"
              >
                <RefreshCw size={15} />
              </button>
            </div>
          )}
          {tab !== "chat" ? (
            <div className="assistant-library-scroll">
              <Library
                key={`${tab}:${libraryVersion}`}
                kind={tab}
                onOpen={setSource}
                onAsk={(content) =>
                  prepare(content, tab === "news" ? "news" : "chat")
                }
              />
              {staff && (
                <div className="assistant-publish">
                  <Button variant="secondary" onClick={() => setEditor(true)}>
                    <Plus size={16} />
                    Добавить материал
                  </Button>
                  <p>
                    Публикация доступна сотрудникам с правом редактирования.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <>
              <div
                className="assistant-transcript"
                ref={transcript}
                onScroll={() => {
                  const el = transcript.current!;
                  const away =
                    el.scrollHeight - el.scrollTop - el.clientHeight > 100;
                  autoScroll.current = !away;
                  setAwayFromBottom(away);
                }}
              >
                {loading ? (
                  <Busy label="Открываем диалог…" />
                ) : (
                  <>
                    <ErrorBox
                      error={loadError}
                      retry={() =>
                        initialId && !conversation
                          ? setParams({
                              conversation: initialId,
                              reload: newRequestId(),
                            })
                          : void refreshHistory()
                      }
                    />
                    {hasOlder && (
                      <button
                        className="assistant-load-older"
                        disabled={checking || busy}
                        onClick={() => void refreshHistory(true)}
                      >
                        <History size={14} />
                        {checking ? "Загружаем…" : "Предыдущие сообщения"}
                      </button>
                    )}
                    {empty && !loadError && (
                      <div className="assistant-welcome">
                        <AgentState
                          status={activeStatus}
                          size="lg"
                          label={
                            staff
                              ? "Сложная заявка? Разберём вместе."
                              : "Разберёмся. И двинемся дальше."
                          }
                          description={
                            staff
                              ? "Соберу факты, подсвечу вопросы и помогу подготовить ответ клиенту."
                              : "Помогу понять рейтинг, подготовить заявку и найти ответы о финансировании."
                          }
                        />
                        <div className="assistant-starters">
                          {starters.map(
                            ({
                              intent: selected,
                              title,
                              text: prompt,
                              icon: Icon,
                            }) => (
                              <button
                                key={title}
                                onClick={() => prepare(prompt, selected)}
                              >
                                <Icon size={19} />
                                <span>{title}</span>
                                <ArrowUpRight size={15} />
                              </button>
                            ),
                          )}
                        </div>
                        <p className="assistant-welcome-foot">
                          <ShieldCheck size={13} />
                          Ответы с опорой на данные и базу знаний
                        </p>
                      </div>
                    )}
                    {turns.map((turn) => (
                      <div className="assistant-turn" key={turn.id}>
                        <div className="assistant-user-message">
                          <div>{turn.user_content}</div>
                          <span>Вы · {date(turn.created_at, true)}</span>
                        </div>
                        {turn.status === "completed" && (
                          <article className="assistant-answer">
                            <div className="assistant-answer-author">
                              <Sparkles size={16} />
                              <strong>Помощник</strong>
                              {turn.intent === "draft_reply" && (
                                <span className="assistant-draft-label">
                                  Черновик для проверки
                                </span>
                              )}
                            </div>
                            <Markdown
                              text={
                                turn.assistant_content ||
                                "Ответ не содержит текста."
                              }
                              sources={turn.sources}
                              onSource={setSource}
                            />
                            <Sources items={turn.sources} onOpen={setSource} />
                            <div className="assistant-answer-footer">
                              <CopyButton text={turn.assistant_content || ""} />
                              <span>
                                <Check size={12} />
                                Ответ готов
                              </span>
                            </div>
                          </article>
                        )}
                        {turn.status === "failed" && (
                          <div className="assistant-failed-turn">
                            <Info size={16} />
                            <div>
                              <strong>Ответ не завершён</strong>
                              <p>
                                Попытка сохранена в истории. Вопрос можно
                                отправить заново.
                              </p>
                              <button
                                onClick={() => {
                                  attempt.current = null;
                                  prepare(turn.user_content, turn.intent);
                                }}
                              >
                                Вернуть вопрос в поле ввода
                                <ArrowUpRight size={13} />
                              </button>
                            </div>
                          </div>
                        )}
                        {turn.status === "pending" && (
                          <div className="assistant-failed-turn">
                            <History size={16} />
                            <div>
                              <strong>Запрос ещё обрабатывается</strong>
                              <p>
                                Обновите историю, чтобы проверить результат.
                                Если обработка прервалась, сервер восстановит
                                состояние после таймаута.
                              </p>
                              <button
                                disabled={checking}
                                onClick={() => void refreshHistory()}
                              >
                                Проверить результат
                                <RefreshCw size={13} />
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                    {busy && (
                      <div className="assistant-turn">
                        <div className="assistant-user-message">
                          <div>{question}</div>
                          <span>Вы · сейчас</span>
                        </div>
                        <article className="assistant-answer">
                          <AgentState
                            status={status}
                            size="sm"
                            label={statusText || "Думаю над ответом"}
                          />
                          {stream && (
                            <div className="assistant-stream-text">
                              <Markdown
                                text={stream}
                                sources={liveSources}
                                onSource={setSource}
                              />
                              <span
                                className="assistant-cursor"
                                aria-hidden="true"
                              />
                            </div>
                          )}
                          {liveSources.length > 0 && (
                            <p className="assistant-live-source-count">
                              <BookOpen size={13} />
                              Найдено материалов: {liveSources.length}
                            </p>
                          )}
                        </article>
                      </div>
                    )}
                  </>
                )}
                <div ref={bottom} />
              </div>
              <div className="assistant-composer-area">
                {awayFromBottom && (
                  <button
                    className="assistant-to-bottom"
                    onClick={() => {
                      autoScroll.current = true;
                      setAwayFromBottom(false);
                      bottom.current?.scrollIntoView({
                        block: "nearest",
                        behavior: "smooth",
                      });
                    }}
                  >
                    <ArrowDown size={14} />К последнему ответу
                  </button>
                )}
                {sendError && (
                  <div className="assistant-send-error" role="alert">
                    <span>{sendError.message}</span>
                    <button
                      onClick={() => {
                        setSendError(null);
                        textarea.current?.focus();
                      }}
                      aria-label="Скрыть сообщение об ошибке"
                    >
                      <X size={14} />
                    </button>
                  </div>
                )}
                <form
                  className={`assistant-composer ${busy ? "is-busy" : ""}`}
                  onSubmit={(e) => void send(e, true)}
                >
                  <div className="assistant-composer-context">
                    <Building2 size={13} />
                    <span>
                      {company?.name ||
                        (applicationId
                          ? "Контекст заявки"
                          : companyId
                            ? "Выбранная компания"
                            : staff
                              ? "Общие вопросы и очередь заявок"
                              : "Общие вопросы о финансировании")}
                      {application &&
                        ` · ${application.number || `Заявка ${application.id}`}`}
                    </span>
                    {conversation && (
                      <span
                        className="assistant-scope-fixed"
                        title="Контекст закреплён за диалогом"
                      >
                        <ShieldCheck size={12} />
                      </span>
                    )}
                  </div>
                  <label className="sr-only" htmlFor="assistant-message">
                    Сообщение помощнику
                  </label>
                  <textarea
                    ref={textarea}
                    id="assistant-message"
                    value={text}
                    onChange={(e) => {
                      setText(e.target.value);
                      if (sendError) setSendError(null);
                    }}
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        if (!busy) void send(undefined, true);
                      }
                    }}
                    placeholder={
                      staff
                        ? "Спросите о заявке, проверках или ответе клиенту…"
                        : "Спросите о рейтинге, кредите или своей заявке…"
                    }
                    maxLength={Math.min(
                      config?.max_message_characters || 6000,
                      6000,
                    )}
                    rows={1}
                    disabled={busy}
                    aria-describedby="assistant-composer-hint"
                  />
                  <div className="assistant-composer-bottom">
                    <label className="assistant-intent">
                      <Sparkles size={14} />
                      <select
                        aria-label="Задача помощника"
                        value={intent}
                        onChange={(e) => setIntent(e.target.value as Intent)}
                        disabled={busy}
                      >
                        {(
                          config?.intents ||
                          (staff
                            ? (Object.keys(INTENTS) as Intent[])
                            : ([
                                "chat",
                                "rating",
                                "advice",
                                "news",
                              ] as Intent[]))
                        ).map((i) => (
                          <option key={i} value={i}>
                            {INTENTS[i]}
                          </option>
                        ))}
                      </select>
                      <ChevronDown size={12} />
                    </label>
                    <div className="assistant-send-actions">
                      {text.length > 5400 && (
                        <span>
                          {text.length} /{" "}
                          {config?.max_message_characters || 6000}
                        </span>
                      )}
                      {busy ? (
                        <button
                          type="button"
                          className="assistant-send is-stop"
                          onClick={() => controller.current?.abort()}
                          aria-label="Остановить ответ"
                        >
                          <Square size={15} />
                        </button>
                      ) : (
                        <button
                          type="submit"
                          className="assistant-send"
                          disabled={blocked || hasPending || !text.trim()}
                          aria-label="Отправить сообщение"
                        >
                          <ArrowUp size={20} />
                        </button>
                      )}
                    </div>
                  </div>
                </form>
                <p
                  className="assistant-composer-hint"
                  id="assistant-composer-hint"
                >
                  {staff
                    ? "Проверьте выводы и черновики. Решение и отправка ответа остаются за вами."
                    : "Помощник может ошибаться. Его рекомендации не являются решением банка."}
                  <span>Enter — отправить · Shift + Enter — новая строка</span>
                </p>
              </div>
            </>
          )}
        </section>
        <aside
          className={`assistant-context ${contextOpen ? "is-open" : ""}`}
          aria-label="Контекст диалога"
        >
          <div className="assistant-context-heading">
            <h2>На чём основан ответ</h2>
            <button
              className="icon-button assistant-context-close"
              onClick={() => setContextOpen(false)}
              aria-label="Закрыть контекст"
            >
              <X size={17} />
            </button>
          </div>
          {contextLoading && (
            <p className="muted small" role="status">
              Загружаем данные…
            </p>
          )}
          <ErrorBox
            error={contextError}
            retry={() => setContextVersion((v) => v + 1)}
          />
          {company ? (
            <div className="assistant-company-context">
              <span className="assistant-company-icon">
                <Building2 size={22} />
              </span>
              <h3>{company.name}</h3>
              <p>
                {company.legal_form_label} · {company.registration_label}
              </p>
              <span>{company.registration_number}</span>
            </div>
          ) : (
            !contextLoading &&
            !contextError && (
              <div className="assistant-general-context">
                <Building2 size={24} />
                <h3>
                  {staff ? "Контекст для работы" : "Начнём с вашего бизнеса"}
                </h3>
                <p>
                  {staff
                    ? "Откройте помощника из карточки заявки, чтобы разобрать её данные."
                    : "Выберите компанию в кабинете, чтобы обсуждать её рейтинг и заявки."}
                </p>
                <Link to={staff ? "/staff" : "/companies"}>
                  {staff ? "Перейти к заявкам" : "Выбрать компанию"}
                  <ArrowRight size={14} />
                </Link>
              </div>
            )
          )}
          {rating ? (
            <section className="assistant-context-rating">
              <div>
                <span>Кредитный рейтинг</span>
                <TrendingUp size={16} />
              </div>
              <p>
                <strong>{rating.score}</strong>
                <span> / {rating.max}</span>
              </p>
              <div
                className="assistant-rating-scale"
                role="meter"
                aria-label="Рейтинг компании"
                aria-valuemin={0}
                aria-valuemax={rating.max}
                aria-valuenow={rating.score}
              >
                <span
                  style={{
                    width: `${Math.min(100, Math.max(0, (rating.score / rating.max) * 100))}%`,
                  }}
                />
              </div>
              <h3>{rating.band_label} рейтинг</h3>
              <small>
                Демонстрационные данные бюро · {date(rating.updated_at)}
              </small>
              <button
                onClick={() =>
                  prepare(
                    staff ? STAFF_STARTERS[0].text : CLIENT_STARTERS[0].text,
                    staff ? "application_review" : "rating",
                  )
                }
              >
                Объяснить рейтинг
                <ArrowUpRight size={14} />
              </button>
            </section>
          ) : (
            company &&
            !contextLoading && (
              <p className="assistant-context-unavailable">
                Рейтинг недоступен. Помощник не будет подставлять выдуманный
                балл.
              </p>
            )
          )}
          {application && (
            <section className="assistant-context-application">
              <span className="assistant-context-caption">
                Выбранная заявка
              </span>
              <h3>{application.number || `Заявка ${application.id}`}</h3>
              <Badge app={application} />
              <dl>
                <div>
                  <dt>Сумма</dt>
                  <dd>{money(application.amount)}</dd>
                </div>
                <div>
                  <dt>Срок</dt>
                  <dd>
                    {application.term_months
                      ? `${application.term_months} мес.`
                      : "Не указан"}
                  </dd>
                </div>
              </dl>
              <Link
                to={`/${staff ? "staff/" : ""}applications/${application.id}`}
              >
                Открыть карточку
                <ArrowUpRight size={14} />
              </Link>
            </section>
          )}
          {!staff &&
            !application &&
            dashboard &&
            dashboard.active_applications.length > 0 && (
              <section className="assistant-context-application">
                <h3>Обсудить заявку</h3>
                {dashboard.active_applications.slice(0, 3).map((a) => (
                  <Link
                    key={a.id}
                    to={assistantUrl({
                      company: companyId || undefined,
                      application: a.id,
                    })}
                  >
                    {a.number || "Черновик заявки"}
                    <ArrowUpRight size={14} />
                  </Link>
                ))}
              </section>
            )}
          <div className="assistant-context-note">
            <ShieldCheck size={17} />
            <p>
              {staff
                ? "Помощник читает данные и готовит черновики. Действия с заявкой выполняете вы."
                : "Помощник видит только данные выбранного контекста. Смена компании создаёт отдельный разговор."}
            </p>
          </div>
          <button
            className="assistant-refresh-context"
            onClick={() => {
              setContextVersion((v) => v + 1);
              void loadConfig();
            }}
            disabled={contextLoading}
          >
            <RefreshCw size={13} />
            Обновить данные
          </button>
        </aside>
      </div>
      <div className="assistant-page-foot">
        <span>
          <ShieldCheck size={13} />
          Демонстрационная среда · Синтетические данные
        </span>
        <Link to="/help">
          Как устроен кабинет
          <ArrowUpRight size={13} />
        </Link>
      </div>
      {source && (
        <SourceViewer
          key={source.id}
          source={source}
          onClose={() => setSource(null)}
        />
      )}
      {editor && (
        <Editor
          onClose={() => setEditor(false)}
          onSaved={() => setLibraryVersion((v) => v + 1)}
        />
      )}
      {deleting && (
        <Modal
          title="Удалить диалог?"
          onClose={() => {
            if (!deleteBusy) setDeleting(null);
          }}
        >
          <p>
            «{deleting.title}» и все его сообщения будут удалены. Вернуть
            историю не получится.
          </p>
          <ErrorBox error={deleteError} />
          <div className="actions">
            <Button
              variant="secondary"
              disabled={deleteBusy}
              onClick={() => setDeleting(null)}
            >
              Оставить
            </Button>
            <Button
              variant="danger"
              busy={deleteBusy}
              onClick={async () => {
                setDeleteBusy(true);
                setDeleteError(null);
                try {
                  await api(
                    `/assistant/conversations/${deleting.id}`,
                    "DELETE",
                  );
                  const active = conversation?.id === deleting.id;
                  setDeleting(null);
                  if (active) startNew();
                  else void loadChats();
                } catch (e) {
                  setDeleteError(e as Error);
                } finally {
                  setDeleteBusy(false);
                }
              }}
            >
              <Trash2 size={16} />
              Удалить диалог
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
