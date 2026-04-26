import { createContext, useContext, useEffect, useState } from "react";
import { jwtDecode } from "jwt-decode";

interface AuthUser {
  name: string | null;
  email: string | null;
  avatarUrl?: string | null;
}

interface AuthContextType {
  token: string | null;
  userId: string | null;
  user: AuthUser | null;
  setToken: (token: string | null) => void;
  setUser: (user: Partial<AuthUser>) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);
const emptyUser = { name: null, email: null, avatarUrl: null };

const getAvatarStorageKey = (userId: string) => `codexa-avatar:${userId}`;

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [token, setTokenState] = useState<string | null>(
    localStorage.getItem("token"),
  );
  const [user, setUserState] = useState<AuthUser>(emptyUser);
  const [userId, setUserId] = useState<string | null>(null);

  const hydrateFromToken = (tokenValue: string | null) => {
    if (!tokenValue) {
      setUserState(emptyUser);
      setUserId(null);
      return;
    }

    try {
      const decoded = jwtDecode<{
        user_id?: string;
        name?: string;
        email?: string;
      }>(tokenValue);
      const nextUserId = decoded.user_id ?? null;

      setUserState({
        name: decoded.name ?? null,
        email: decoded.email ?? null,
        avatarUrl: nextUserId
          ? localStorage.getItem(getAvatarStorageKey(nextUserId))
          : null,
      });
      setUserId(nextUserId);
    } catch {
      setUserState(emptyUser);
      setUserId(null);
    }
  };

  const setToken = (newToken: string | null) => {
    if (newToken) {
      localStorage.setItem("token", newToken);
      setTokenState(newToken);
      hydrateFromToken(newToken);
      return;
    }

    localStorage.removeItem("token");
    setTokenState(null);
    setUserId(null);
    setUserState(emptyUser);
  };

  const setUser = (nextUser: Partial<AuthUser>) => {
    setUserState((prev) => ({
      ...prev,
      name: nextUser.name ?? prev.name ?? null,
      email: nextUser.email ?? prev.email ?? null,
      avatarUrl: nextUser.avatarUrl ?? prev.avatarUrl ?? null,
    }));
  };

  const logout = () => {
    localStorage.removeItem("token");
    setTokenState(null);
    setUserId(null);
    setUserState(emptyUser);
  };

  useEffect(() => {
    hydrateFromToken(token);
  }, [token]);

  return (
    <AuthContext.Provider value={{ token, userId, user, setToken, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  return useContext(AuthContext) as AuthContextType;
};
