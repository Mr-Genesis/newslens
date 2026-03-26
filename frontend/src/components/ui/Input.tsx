"use client";

import { cn } from "@/lib/utils";
import { forwardRef } from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
  leftIcon?: React.ReactNode;
  rightAction?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { error = false, leftIcon, rightAction, className, ...props },
  ref
) {
  return (
    <div className="relative flex items-center">
      {leftIcon && (
        <span className="absolute left-3 text-[var(--text-muted)] pointer-events-none">
          {leftIcon}
        </span>
      )}
      <input
        ref={ref}
        className={cn(
          "w-full h-12 px-4 rounded-[var(--radius-md)]",
          "bg-[var(--surface)] border text-[var(--text-primary)]",
          "text-[15px] placeholder:text-[var(--text-ghost)]",
          "transition-all duration-[var(--duration-short)]",
          "focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[var(--bg)]",
          error
            ? "border-[var(--dismiss)] focus:ring-[var(--dismiss)]"
            : "border-[var(--border)] focus:ring-[var(--accent)]",
          leftIcon && "pl-10",
          rightAction && "pr-12",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          className
        )}
        {...props}
      />
      {rightAction && (
        <span className="absolute right-2">{rightAction}</span>
      )}
    </div>
  );
});
