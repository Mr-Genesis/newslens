"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { signInEmail, signInWithGoogle, signUpEmail } from "@/lib/firebase";

type Mode = "signin" | "signup";

export default function LoginPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) router.replace("/"); // already signed in → home
  }, [user, router]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^Firebase:\s*/, "") : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const emailDisabled = busy || !email.trim() || pw.length < 6;

  return (
    <div className="mx-auto flex min-h-[70dvh] max-w-sm flex-col justify-center gap-6 px-6">
      <header className="space-y-1">
        <h1 className="text-3xl text-white" style={{ fontFamily: "var(--font-fraunces)" }}>
          Welcome to NewsLens
        </h1>
        <p className="text-sm text-white/50">Sign in to keep your topics, saves, and reading across devices.</p>
      </header>

      <button
        onClick={() => run(signInWithGoogle)}
        disabled={busy}
        className="flex h-12 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 text-sm font-medium text-white transition hover:bg-white/10 disabled:opacity-50"
      >
        Continue with Google
      </button>

      <div className="flex items-center gap-3 text-xs text-white/30">
        <span className="h-px flex-1 bg-white/10" /> or <span className="h-px flex-1 bg-white/10" />
      </div>

      <div className="space-y-3">
        <input
          type="email"
          inputMode="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          className="h-12 w-full rounded-xl border border-white/10 bg-white/5 px-4 text-sm text-white placeholder:text-white/30 focus:border-[#F97316] focus:outline-none"
        />
        <input
          type="password"
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          placeholder="Password (min 6 characters)"
          className="h-12 w-full rounded-xl border border-white/10 bg-white/5 px-4 text-sm text-white placeholder:text-white/30 focus:border-[#F97316] focus:outline-none"
        />
        <button
          onClick={() => run(() => (mode === "signin" ? signInEmail(email, pw) : signUpEmail(email, pw)))}
          disabled={emailDisabled}
          className="h-12 w-full rounded-xl bg-[#F97316] text-sm font-semibold text-black transition hover:brightness-110 disabled:opacity-40"
        >
          {busy ? "…" : mode === "signin" ? "Sign in" : "Create account"}
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        onClick={() => {
          setMode((m) => (m === "signin" ? "signup" : "signin"));
          setError(null);
        }}
        className="text-center text-xs text-white/50 underline-offset-4 hover:underline"
      >
        {mode === "signin" ? "New here? Create an account" : "Have an account? Sign in"}
      </button>
    </div>
  );
}
