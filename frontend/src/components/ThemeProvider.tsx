"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
} from "react";

type Theme = "dark" | "light" | "auto";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  resolvedTheme: "dark" | "light";
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  setTheme: () => {},
  resolvedTheme: "dark",
});

export function useTheme() {
  return useContext(ThemeContext);
}

function getSystemTheme(): "dark" | "light" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function resolveTheme(theme: Theme): "dark" | "light" {
  if (theme === "auto") return getSystemTheme();
  return theme;
}

function applyTheme(resolved: "dark" | "light") {
  const el = document.documentElement;
  if (resolved === "light") {
    el.classList.add("light");
  } else {
    el.classList.remove("light");
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");
  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">("dark");

  // Initialize from localStorage
  useEffect(() => {
    const stored = localStorage.getItem("newslens-theme") as Theme | null;
    const t = stored || "dark";
    setThemeState(t);
    const resolved = resolveTheme(t);
    setResolvedTheme(resolved);
    applyTheme(resolved);
  }, []);

  // Listen for system theme changes when in auto mode
  useEffect(() => {
    if (theme !== "auto") return;

    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const handler = () => {
      const resolved = resolveTheme("auto");
      setResolvedTheme(resolved);
      applyTheme(resolved);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem("newslens-theme", t);
    const resolved = resolveTheme(t);
    setResolvedTheme(resolved);
    applyTheme(resolved);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
