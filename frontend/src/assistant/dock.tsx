import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createSearchParams, useLocation, useNavigate, useSearchParams, type SetURLSearchParams } from "react-router-dom";
import { ArrowUpRight, MessageSquareText, Minimize2, Plus, X } from "lucide-react";
import { useSession } from "../context";
import { AssistantWorkspace } from "./page";
import { newRequestId } from "./id";
import "./dock.css";

export function AssistantDock({ company, application }: { company?: number; application?: number }) {
  const { user } = useSession();
  const location = useLocation(), navigate = useNavigate(), [routeParams] = useSearchParams();
  const full = location.pathname === "/assistant";
  const [open, setOpen] = useState(false), [loaded, setLoaded] = useState(full);
  const [localParams, setLocalParams] = useState(() => new URLSearchParams());
  const [top, setTop] = useState(80), [mobile, setMobile] = useState(innerWidth <= 640);
  const [minimizing, setMinimizing] = useState(false);
  const returnUrl = useRef(""), previousFocus = useRef<HTMLElement | null>(null);
  const openedScope = useRef("");
  const panel = useRef<HTMLElement>(null), launcher = useRef<HTMLButtonElement>(null);
  const current = useRef({ full, params: routeParams });
  current.current = { full, params: full ? routeParams : localParams };
  const params = full ? routeParams : localParams;

  useEffect(() => {
    if (!full) returnUrl.current = location.pathname + location.search;
  }, [full, location.pathname, location.search]);

  const changeParams = useCallback<SetURLSearchParams>((next, options) => {
    const value = typeof next === "function" ? next(current.current.params) : next;
    const q = createSearchParams(value);
    if (current.current.full) navigate(`/assistant?${q}`, options);
    else setLocalParams(q);
  }, [navigate]);

  const show = useCallback((scope?: { company?: number | string; application?: number | string; intent?: string }) => {
    previousFocus.current = document.activeElement as HTMLElement;
    const wantedCompany = scope?.company ?? company;
    const wantedApplication = scope?.application ?? application;
    // Reuse a draft/dialogue only inside the scope in which it was opened.
    const scopeKey = `${wantedCompany || ""}:${wantedApplication || ""}`;
    if (!loaded || openedScope.current !== scopeKey || (scope?.intent && scope.intent !== "chat")) {
      const q = new URLSearchParams();
      if (wantedCompany) q.set("company", String(wantedCompany));
      if (wantedApplication) q.set("application", String(wantedApplication));
      if (scope?.intent) q.set("intent", scope.intent);
      setLocalParams(q);
    }
    openedScope.current = scopeKey;
    setLoaded(true); setOpen(true); setMinimizing(false);
  }, [company, application, localParams, loaded]);

  const close = useCallback(() => {
    const finish = () => { setOpen(false); setMinimizing(false); (previousFocus.current?.isConnected ? previousFocus.current : launcher.current)?.focus(); };
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { finish(); return; }
    setMinimizing(true);
    const motion = panel.current?.animate([{ opacity: 1, transform: "translateY(0)" }, { opacity: 0, transform: "translateY(12px)" }], { duration: 160, easing: "ease-in" });
    if (motion) motion.onfinish = finish; else finish();
  }, []);

  useEffect(() => {
    const listener = (event: Event) => show((event as CustomEvent).detail);
    window.addEventListener("delo:assistant-open", listener);
    return () => window.removeEventListener("delo:assistant-open", listener);
  }, [show]);
  useEffect(() => {
    const header = document.querySelector(".site-header");
    const measure = () => { setTop(header?.getBoundingClientRect().height || 80); setMobile(innerWidth <= 640); };
    measure();
    const observer = new ResizeObserver(measure);
    if (header) observer.observe(header);
    window.addEventListener("resize", measure);
    return () => { observer.disconnect(); window.removeEventListener("resize", measure); };
  }, []);
  useEffect(() => {
    if (!full && open) panel.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus({ preventScroll: true });
    if (!open || full) return;
    const roots = [document.querySelector<HTMLElement>(".site-header"), document.querySelector<HTMLElement>("#main")];
    const previous = roots.map(el => el?.inert || false);
    const overflow = document.body.style.overflow;
    if (mobile) { roots.forEach(el => { if (el) el.inert = true; }); document.body.style.overflow = "hidden"; }
    const keys = (event: KeyboardEvent) => {
      if (document.querySelector("dialog[open]")) return;
      if (event.key === "Escape") { event.preventDefault(); close(); }
      if (event.key === "Tab" && mobile) {
        const elements = [...(panel.current?.querySelectorAll<HTMLElement>("button:not(:disabled),a[href],textarea:not(:disabled),select:not(:disabled),input:not(:disabled)") || [])].filter(el => el.getClientRects().length);
        const first = elements[0], last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", keys);
    return () => { roots.forEach((el, i) => { if (el) el.inert = previous[i]; }); document.body.style.overflow = overflow; document.removeEventListener("keydown", keys); };
  }, [open, full, mobile, close]);

  function expand() {
    returnUrl.current = location.pathname + location.search;
    navigate(`/assistant?${localParams}`);
  }
  function minimize() {
    openedScope.current = `${company || ""}:${application || ""}`;
    setLocalParams(new URLSearchParams(routeParams)); setLoaded(true); setOpen(true);
    navigate(returnUrl.current || (company ? `/companies/${company}` : user?.role === "EMPLOYEE" ? "/staff" : "/companies"));
  }

  return <>
    {!full && !open && <button ref={launcher} className="assistant-launcher" onClick={() => show()}>
      <span className="assistant-dock-symbol"><MessageSquareText size={27} strokeWidth={1.7} aria-hidden="true" /></span>
      <span><strong>Дело рядом</strong><small>Помощник по бизнесу</small></span>
    </button>}
    {(loaded || full) && <section ref={panel} hidden={!full && !open}
      className={`assistant-dock-panel ${full ? "is-full" : "is-compact"} ${minimizing ? "is-minimizing" : ""}`}
      role={full ? undefined : "dialog"} aria-label={full ? "Помощник по бизнесу" : "Дело рядом"}
      aria-modal={!full && mobile ? true : undefined}
      style={{ "--dock-header-height": `${top}px` } as CSSProperties}>
      {full ? <button className="assistant-minimize" onClick={minimize}><Minimize2 size={16} />Свернуть в чат</button> :
        <div className="assistant-dock-heading"><span className="assistant-dock-symbol"><MessageSquareText size={25} strokeWidth={1.7} aria-hidden="true" /></span>
          <div><h2>Дело рядом</h2><p>Разберёмся, не уходя из кабинета.</p></div>
          <button className="icon-button" aria-label="Новый диалог" onClick={() => { const q = new URLSearchParams(); if (company) q.set("company", String(company)); if (application) q.set("application", String(application)); q.set("new", newRequestId()); setLocalParams(q); }}><Plus size={18} /></button>
          <button className="icon-button" onClick={close} aria-label="Закрыть помощника"><X size={19} /></button>
        </div>}
      <AssistantWorkspace key={`${user!.id}:${params.toString()}`} params={params} onParamsChange={changeParams} />
      {!full && <button className="assistant-dock-expand" onClick={expand}>Открыть на весь экран<ArrowUpRight size={16} /></button>}
    </section>}
  </>;
}
