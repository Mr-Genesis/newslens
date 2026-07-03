"use client";

import Link from "next/link";
import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/components/AuthProvider";
import { signOut } from "@/lib/firebase";

/**
 * Account section for Settings — the entry point into the sign-in flow.
 * The /login page existed but nothing in the app linked to it, so auth was
 * unreachable in practice. Signed out → CTA to /login; signed in → identity + sign out.
 */
export function AccountCard() {
  const { user, loading } = useAuth();
  const [busy, setBusy] = useState(false);

  return (
    <Card variant="raised">
      <div className="p-3.5">
        <h2 className="text-heading text-[var(--text-primary)] mb-1">Account</h2>
        {loading ? (
          <div className="skeleton h-9 w-full" />
        ) : user ? (
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-small text-[var(--text-secondary)] truncate">
                {user.displayName || user.email || "Signed in"}
              </p>
              {user.email && user.displayName && (
                <p className="text-mono text-[var(--text-ghost)] truncate">{user.email}</p>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              loading={busy}
              onClick={() => {
                setBusy(true);
                signOut()
                  .catch(() => {})
                  .finally(() => setBusy(false));
              }}
            >
              Sign out
            </Button>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <p className="text-mono text-[var(--text-ghost)]">
              Sign in to keep your reading, follows and settings across devices
            </p>
            <Link
              href="/login"
              className="shrink-0 rounded-[var(--radius-md)] bg-[var(--accent)] px-4 py-2 text-small font-medium text-[#0C0C0E] transition-opacity hover:opacity-90"
            >
              Sign in
            </Link>
          </div>
        )}
      </div>
    </Card>
  );
}
