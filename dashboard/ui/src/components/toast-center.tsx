"use client";

import { createContext, ReactNode, useContext, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Info, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastTone = "info" | "success" | "warning" | "error";

type ToastItem = {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
};

type ToastContextValue = {
  pushToast: (toast: Omit<ToastItem, "id">) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const toneClasses: Record<ToastTone, string> = {
  info: "border-blue-200/70 bg-[rgba(246,250,253,0.92)] text-slate-900 dark:border-blue-500/20 dark:bg-[rgba(19,27,38,0.92)] dark:text-slate-50",
  success: "border-emerald-200/70 bg-[rgba(245,252,248,0.94)] text-slate-900 dark:border-emerald-500/20 dark:bg-[rgba(18,31,27,0.94)] dark:text-slate-50",
  warning: "border-amber-200/80 bg-[rgba(255,249,238,0.94)] text-slate-900 dark:border-amber-500/20 dark:bg-[rgba(36,28,17,0.94)] dark:text-slate-50",
  error: "border-rose-200/80 bg-[rgba(255,246,248,0.94)] text-slate-900 dark:border-rose-500/20 dark:bg-[rgba(37,22,27,0.94)] dark:text-slate-50",
};

const toneIcons: Record<ToastTone, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  error: AlertCircle,
};

const toneIconClasses: Record<ToastTone, string> = {
  info: "text-blue-600 dark:text-blue-300",
  success: "text-emerald-600 dark:text-emerald-300",
  warning: "text-amber-600 dark:text-amber-300",
  error: "text-rose-600 dark:text-rose-300",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const counterRef = useRef(0);

  const value = useMemo<ToastContextValue>(
    () => ({
      pushToast: ({ title, description, tone }) => {
        counterRef.current += 1;
        const id = `toast-${Date.now()}-${counterRef.current}`;
        setToasts((current) => [...current, { id, title, description, tone }].slice(-5));
        window.setTimeout(() => {
          setToasts((current) => current.filter((item) => item.id !== id));
        }, 5000);
      },
    }),
    [],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[80] flex w-[min(92vw,380px)] flex-col gap-3">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              "soft-enter pointer-events-auto rounded-[18px] border px-4 py-3 shadow-[0_24px_60px_-30px_rgba(15,23,42,0.28)] backdrop-blur-xl",
              toneClasses[toast.tone],
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3">
                {(() => {
                  const Icon = toneIcons[toast.tone];
                  return <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", toneIconClasses[toast.tone])} />;
                })()}
                <div className="min-w-0">
                  <div className="font-semibold">{toast.title}</div>
                {toast.description ? <div className="mt-1 break-words text-sm text-slate-500 dark:text-slate-400">{toast.description}</div> : null}
                </div>
              </div>
              <button
                type="button"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl border border-slate-200 text-slate-500 transition hover:bg-slate-50 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-900"
                onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToasts() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToasts must be used inside ToastProvider");
  }
  return context;
}
