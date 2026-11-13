import { createContext, useContext, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { open, session } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => session.read()?.user ?? null);
  // True after a deliberate log out, so protected pages go to the landing page instead of the log in pop-up.
  const [signedOut, setSignedOut] = useState(false);

  // The backend returns { access, refresh, user } for both log in and sign up.
  const start = (data) => {
    if (typeof data?.access !== "string" || typeof data?.refresh !== "string" || !data?.user) {
      throw new Error("The server sent an unexpected response. Try again.");
    }
    session.save(data);
    setSignedOut(false);
    setUser(data.user);
  };
  const value = {
    user,
    signedOut,
    login: async (email, password) => start(await open("/api/auth/login/", { email, password })),
    signup: async (form) => start(await open("/api/auth/signup/", form)),
    logout: () => {
      session.clear();
      setSignedOut(true);
      setUser(null);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Wrap any page that needs a login. Without one, open the log in pop-up and remember where the person was going.
export function RequireAuth({ children }) {
  const { user, signedOut } = useAuth();
  const location = useLocation();
  if (user) return children;
  if (signedOut) return <Navigate to="/" replace />;
  return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
}
