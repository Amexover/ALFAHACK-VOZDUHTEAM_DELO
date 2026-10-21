import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "./api";
import type { User, Config } from "./types";
interface Session {
  user: User | null;
  config: Config | null;
  loading: boolean;
  error: Error | null;
  setUser: (u: User | null) => void;
  retry: () => void;
}
const Context = createContext<Session>(null!);
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null),
    [config, setConfig] = useState<Config | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState<Error | null>(null);
  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api<Config>("/config"),
      api<{ user: User }>("/auth/me").catch((e) => {
        if (e.status === 401) return null;
        throw e;
      }),
    ])
      .then(([c, u]) => {
        setConfig(c);
        setUser(u?.user || null);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    retry();
    const expired = () => setUser(null);
    window.addEventListener("delo:session-expired", expired);
    return () => window.removeEventListener("delo:session-expired", expired);
  }, [retry]);
  return (
    <Context.Provider value={{ user, config, loading, error, setUser, retry }}>
      {children}
    </Context.Provider>
  );
}
export const useSession = () => useContext(Context);
export function useResource<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState<Error | null>(null),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((x) => x + 1), []);
  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    api<T>(path, "GET", undefined, ctrl.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [path, version]);
  return { data, error, loading, refresh, setData };
}
