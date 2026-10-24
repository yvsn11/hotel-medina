import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, setToken, setUnauthorizedHandler, type User } from '../services/api';
import { safeStorageGet, safeStorageRemove, safeStorageSet } from '../lib/format';

const STORAGE_KEY = 'medina.auth';

interface AuthState {
  user: User | null;
  token: string | null;
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (email: string, password: string, fullName: string) => Promise<User>;
  logout: () => void;
  clearSessionExpired: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function loadStored(): { token: string; user: User } | null {
  const raw = safeStorageGet(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.token === 'string' && parsed.user && typeof parsed.user.id === 'number') {
      return parsed;
    }
  } catch {
    /* corrupted */
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<{ token: string; user: User } | null>(() => {
    const stored = loadStored();
    setToken(stored?.token ?? null);
    return stored;
  });
  const [sessionExpired, setSessionExpired] = useState(false);

  const store = useCallback((s: { token: string; user: User } | null) => {
    setToken(s?.token ?? null);
    setSession(s);
    if (s) safeStorageSet(STORAGE_KEY, JSON.stringify(s));
    else safeStorageRemove(STORAGE_KEY);
  }, []);

  const logout = useCallback(() => store(null), [store]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      store(null);
      setSessionExpired(true);
    });
    return () => setUnauthorizedHandler(null);
  }, [store]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.login({ email, password });
      setSessionExpired(false);
      store(res);
      return res.user;
    },
    [store],
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const res = await api.register({ email, password, full_name: fullName });
      setSessionExpired(false);
      store(res);
      return res.user;
    },
    [store],
  );

  const value = useMemo<AuthState>(
    () => ({
      user: session?.user ?? null,
      token: session?.token ?? null,
      sessionExpired,
      login,
      register,
      logout,
      clearSessionExpired: () => setSessionExpired(false),
    }),
    [session, sessionExpired, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
