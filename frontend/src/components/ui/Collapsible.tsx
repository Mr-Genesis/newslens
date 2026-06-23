"use client";

import { useState, type ReactNode } from "react";

/** Brief-by-default accordion row (v4): label + preview when collapsed, body on tap. */
export function Collapsible({
  label,
  preview,
  defaultOpen = false,
  children,
}: {
  label: string;
  preview?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-[var(--border-subtle)]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-3 py-3 text-left"
      >
        <span className="text-mono text-[var(--text-secondary)] w-24 shrink-0">{label}</span>
        {!open && (
          <span className="text-small text-[var(--text-muted)] flex-1 truncate">{preview}</span>
        )}
        <span className="text-[var(--text-ghost)] ml-auto" aria-hidden="true">
          {open ? "–" : "›"}
        </span>
      </button>
      {open && <div className="pb-4">{children}</div>}
    </div>
  );
}
