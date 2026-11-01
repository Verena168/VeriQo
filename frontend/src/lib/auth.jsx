import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  const refresh = useCallback(async () => {
    if (!getToken()) return setUser(null);
    try {
      setUser(await api("/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onLogout = () => setUser(null);
    window.addEventListener("veriqo:logout", onLogout);
    return () => window.removeEventListener("veriqo:logout", onLogout);
  }, [refresh]);

  const accept = (res) => {
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const value = {
    user,
    loading,
    refresh,
    login: async (email, password) => accept(await api("/auth/login", { method: "POST", body: { email, password } })),
    register: async (data) => accept(await api("/auth/register", { method: "POST", body: data })),
    logout: () => {
      setToken(null);
      setUser(null);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
