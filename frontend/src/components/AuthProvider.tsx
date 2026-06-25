"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { onIdTokenChanged, type User } from "firebase/auth";
import { auth } from "@/lib/firebase";

// onIdTokenChanged (not onAuthStateChanged) also fires on the silent ~1h token refresh,
// keeping global auth state current without a re-login.
const AuthCtx = createContext<{ user: User | null; loading: boolean }>({
  user: null,
  loading: true,
});

export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!auth) {
      setLoading(false); // SSR / Firebase not configured: never block render
      return;
    }
    return onIdTokenChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
    });
  }, []);

  return <AuthCtx.Provider value={{ user, loading }}>{children}</AuthCtx.Provider>;
}
