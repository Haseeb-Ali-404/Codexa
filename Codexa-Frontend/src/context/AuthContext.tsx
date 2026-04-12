import { createContext, useContext, useEffect, useState } from "react";
import {jwtDecode} from "jwt-decode";

interface AuthContextType {
  token: string | null;
  userId: string | null;
  user: {name: string | null, email: string | null} | null;
  setToken: (token: string | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  
  const [token, setTokenState] = useState<string | null>(
    localStorage.getItem("token")
  );
  const [user, setUser] = useState({
    name: null,
    email: null,
  });

  const [userId, setUserId] = useState<string | null>(null);

  // -------- Decode userId from token --------
  const getUserIdFromToken = (token: string): string | null => {
    try {
      const decoded: any = jwtDecode(token);
      console.log(decoded);
      setUser(decoded);
      return decoded.user_id || null; // "sub" contains user_id
    } catch {
      return null;
    }
  };

  // -------- Set token and decode user id --------
  const setToken = (newToken: string | null) => {
    if (newToken) {
      localStorage.setItem("token", newToken);
      setTokenState(newToken);
      setUserId(getUserIdFromToken(newToken));
    } else {
      localStorage.removeItem("token");
      setTokenState(null);
      setUserId(null);
    }
  };

  // -------- Logout --------
  const logout = () => {
    localStorage.removeItem("token");
    setTokenState(null);
    setUserId(null);
  };

  // Decode token on initial load
  useEffect(() => {
    if (token) {
      setUserId(getUserIdFromToken(token));
    }
  }, []);

  return (
    <AuthContext.Provider value={{ token, userId, setToken, logout, user }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  return useContext(AuthContext) as AuthContextType;
};
