"use client";

import { useState, useCallback } from "react";

export type ToastVariant = "info" | "success" | "error" | "action";

export interface Toast {
  id: string;
  message: string;
  variant: ToastVariant;
  action?: { label: string; onClick: () => void };
}

let toastId = 0;

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback(
    (
      message: string,
      variant: ToastVariant = "info",
      action?: { label: string; onClick: () => void }
    ) => {
      const id = String(++toastId);
      setToasts((prev) => [...prev, { id, message, variant, action }]);

      if (!action) {
        setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 3000);
      }

      return id;
    },
    []
  );

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, addToast, removeToast };
}
