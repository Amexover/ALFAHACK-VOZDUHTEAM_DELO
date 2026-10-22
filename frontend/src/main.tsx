import React, {
  lazy,
  Suspense,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { ChevronDown, LogOut, Sparkles } from "lucide-react";
import { api } from "./api";
import { SessionProvider, useResource, useSession } from "./context";
import { ApplicationPage } from "./application";
import {
  ApplicationsPage,
  Companies,
  DashboardPage,
  Help,
  Login,
  ModePage,
  NewsPage,
} from "./client";
import { StaffCard, StaffQueue } from "./staff";
import { Wizard } from "./wizard";
import { Busy, Button, ErrorBox } from "./ui";
import type { Application, Company, Role } from "./types";
import { assistantUrl } from "./assistant/entry";
import type { Conversation } from "./assistant/types";
import "./tailwind.css";
import "./styles.css";
const AssistantPage = lazy(() =>
  import("./assistant/page").then((m) => ({ default: m.AssistantPage })),
);
class Boundary extends React.Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <main className="fatal">
        <h1>Не удалось открыть страницу</h1>
        <p>
          Обновите кабинет. Сохранённые на сервере заявки останутся на месте.
        </p>
        <Button onClick={() => window.location.reload()}>
          Обновить страницу
        </Button>
      </main>
    ) : (
      this.props.children
    );
  }
}
function Protected({ role }: { role?: Role }) {
  const { user } = useSession();
  if (!user) return <Navigate to="/login" replace />;
  if (role && user.role !== role)
    return (
      <Navigate
        to={user.role === "EMPLOYEE" ? "/staff" : "/companies"}
        replace
      />
    );
  return <Outlet />;
}
function Frame() {
  const { user, setUser } = useSession(),
    location = useLocation(),
    nav = useNavigate();
  const assistantParams = new URLSearchParams(location.search);
  const assistantConversation = useResource<Conversation>(
    location.pathname === "/assistant" && assistantParams.get("conversation")
      ? `/assistant/conversations/${encodeURIComponent(assistantParams.get("conversation")!)}`
      : null,
  );
  const companyMatch = location.pathname.match(/^\/companies\/(\d+)/),
    appMatch = location.pathname.match(/^\/applications\/(\d+)/);
  const app = useResource<Application>(
    appMatch ? `/applications/${appMatch[1]}` : null,
  );
  const companies = useResource<{ items: Company[] }>(
    user!.role === "CLIENT"
      ? `/companies?view=${companyMatch?.[1] || ""}`
      : null,
  );
  const cid =
    Number(
      companyMatch?.[1] ||
        (location.pathname === "/assistant" &&
        assistantConversation.data?.id === assistantParams.get("conversation")
          ? assistantConversation.data?.company_id
          : null) ||
        (location.pathname === "/assistant"
          ? assistantParams.get("company")
          : null) ||
        app.data?.company_id ||
        localStorage.getItem(`delo:company:${user!.id}`),
    ) || 0;
  const [logoutBusy, setLogoutBusy] = useState(false),
    [logoutError, setLogoutError] = useState<Error | null>(null);
  useEffect(() => {
    if (companyMatch)
      localStorage.setItem(`delo:company:${user!.id}`, companyMatch[1]);
  }, [companyMatch?.[1], user!.id]);
  useEffect(() => {
    window.scrollTo(0, 0);
    document.getElementById("main")?.focus({ preventScroll: true });
    document.title = `Дело — ${user!.role === "EMPLOYEE" ? "кабинет сотрудника" : "кредиты для бизнеса"}`;
  }, [location.pathname]);
  async function logout() {
    setLogoutBusy(true);
    setLogoutError(null);
    try {
      await api("/auth/logout", "POST");
      setUser(null);
      nav("/login");
    } catch (e) {
      setLogoutError(e as Error);
    } finally {
      setLogoutBusy(false);
    }
  }
  const client = user!.role === "CLIENT";
  return (
    <>
      <a className="skip-link" href="#main">
        К содержимому
      </a>
      <header className="site-header">
        <div className="nav-inner">
          <Link
            className="brand"
            to={
              client && cid
                ? `/companies/${cid}`
                : client
                  ? "/companies"
                  : "/staff"
            }
            aria-label="Дело — главная"
          >
            дело<span>.</span>
          </Link>
          <nav aria-label="Основная навигация">
            {client ? (
              <>
                <NavLink end to={cid ? `/companies/${cid}` : "/companies"}>
                  Обзор
                </NavLink>
                {cid > 0 && (
                  <>
                    <NavLink to={`/companies/${cid}/applications`}>
                      Мои заявки
                    </NavLink>
                    <NavLink to={`/companies/${cid}/news`}>Для бизнеса</NavLink>
                  </>
                )}
              </>
            ) : (
              <NavLink to="/staff" end>
                Заявки бизнеса
              </NavLink>
            )}
            <NavLink
              className="assistant-nav-link"
              to={assistantUrl({ company: client ? cid : undefined })}
            >
              <Sparkles size={14} />
              Помощник
            </NavLink>
            <NavLink to="/help">Помощь</NavLink>
          </nav>
          <div className="account">
            {client ? (
              <div className="company-select">
                <select
                  aria-label="Выбранная компания"
                  value={
                    companies.data?.items.some((c) => c.id === cid) ? cid : ""
                  }
                  onChange={(e) => {
                    if (e.target.value === "change") nav("/companies");
                    else if (e.target.value)
                      nav(`/companies/${e.target.value}`);
                  }}
                >
                  <option value="">Выберите бизнес</option>
                  {companies.data?.items.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                  <option value="change">Добавить или выбрать бизнес…</option>
                </select>
                <ChevronDown size={13} />
              </div>
            ) : (
              <span className="employee-name">{user!.full_name}</span>
            )}
            <span className="avatar" aria-hidden="true">
              {user!.full_name
                .split(" ")
                .slice(0, 2)
                .map((s) => s[0])
                .join("")}
            </span>
            <button
              disabled={logoutBusy}
              className="icon-button logout"
              title="Выйти"
              aria-label="Выйти из кабинета"
              onClick={logout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        className={`workspace ${client ? "" : "staff-workspace"}`}
      >
        <ErrorBox error={logoutError} />
        <Outlet />
        <footer className="site-footer">
          <p>Демонстрационный кабинет. Все данные вымышлены.</p>
          <div>
            <Link to="/help">Помощь</Link>
            <span>Дело / 2026</span>
          </div>
        </footer>
      </main>
    </>
  );
}
function App() {
  const s = useSession();
  if (s.loading) return <Busy label="Открываем кабинет…" />;
  if (s.error)
    return (
      <main className="fatal">
        <ErrorBox error={s.error} retry={s.retry} />
      </main>
    );
  return (
    <Routes>
      <Route
        path="/login"
        element={
          s.user ? (
            <Navigate
              replace
              to={s.user.role === "EMPLOYEE" ? "/staff" : "/companies"}
            />
          ) : (
            <Login />
          )
        }
      />
      <Route element={<Protected />}>
        <Route element={<Frame />}>
          <Route path="/help" element={<Help />} />
          <Route
            path="/assistant"
            element={
              <Suspense fallback={<Busy label="Открываем помощника…" />}>
                <AssistantPage />
              </Suspense>
            }
          />
          <Route element={<Protected role="CLIENT" />}>
            <Route path="/companies" element={<Companies />} />
            <Route path="/companies/:companyId" element={<DashboardPage />} />
            <Route path="/companies/:companyId/new" element={<ModePage />} />
            <Route
              path="/companies/:companyId/applications"
              element={<ApplicationsPage />}
            />
            <Route path="/companies/:companyId/news" element={<NewsPage />} />
            <Route path="/applications/:id/edit/:step" element={<Wizard />} />
            <Route path="/applications/:id" element={<ApplicationPage />} />
          </Route>
          <Route element={<Protected role="EMPLOYEE" />}>
            <Route path="/staff" element={<StaffQueue />} />
            <Route path="/staff/applications/:id" element={<StaffCard />} />
          </Route>
          <Route
            path="*"
            element={
              <Navigate
                to={s.user?.role === "EMPLOYEE" ? "/staff" : "/companies"}
                replace
              />
            }
          />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Boundary>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
    </Boundary>
  </React.StrictMode>,
);
