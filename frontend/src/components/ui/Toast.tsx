"use client";

import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import type { Toast as ToastType } from "@/hooks/useToast";

const variantStyles: Record<string, string> = {
  info: "bg-[var(--surface-raised)] text-[var(--text-primary)]",
  success: "bg-[var(--agree-muted)] text-[var(--agree)]",
  error: "bg-[var(--dismiss-muted)] text-[var(--dismiss)]",
  action: "bg-[var(--surface-raised)] text-[var(--text-primary)]",
};

interface ToastContainerProps {
  toasts: ToastType[];
  onRemove: (id: string) => void;
}

export function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  return (
    <div className="fixed bottom-[calc(var(--tab-bar-height)+var(--safe-bottom)+var(--space-sm))] left-[var(--space-md)] right-[var(--space-md)] z-50 flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className={cn(
              "rounded-[var(--radius-lg)] px-4 py-3 shadow-[var(--shadow-lg)] pointer-events-auto",
              "glass flex items-center gap-3",
              variantStyles[toast.variant]
            )}
          >
            <span className="text-[14px] font-medium flex-1">
              {toast.message}
            </span>
            {toast.action && (
              <button
                onClick={() => {
                  toast.action?.onClick();
                  onRemove(toast.id);
                }}
                className="text-[var(--accent)] text-[13px] font-semibold shrink-0"
              >
                {toast.action.label}
              </button>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
