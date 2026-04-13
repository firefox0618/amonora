"use client";

import { ReactNode } from "react";
import { X } from "lucide-react";
import { cn, statusTone } from "@/lib/utils";

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "control-noise glass-hover min-w-0 rounded-[12px] border border-[color:var(--surface-border)] bg-[var(--surface)] p-3 shadow-[0_14px_32px_-28px_rgba(15,23,32,0.16)] backdrop-blur-[22px]",
        "dark:border-[color:var(--surface-border)] dark:bg-[var(--surface)] dark:shadow-[0_18px_48px_-36px_rgba(2,6,23,0.82)]",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function MetricCard({
  label,
  value,
  helper,
  className,
}: {
  label: string;
  value: ReactNode;
  helper: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("space-y-1.5 overflow-hidden", className)}>
      <p className="break-words text-[11px] font-semibold uppercase tracking-[0.2em] text-[color:var(--text-muted)]">{label}</p>
      <div className="break-words text-[clamp(1.1rem,1.2vw,1.5rem)] font-semibold leading-tight tracking-[-0.05em] text-slate-950 dark:text-slate-50">
        {value}
      </div>
      <p className="break-words text-[12px] leading-5 text-[color:var(--text-muted)]">{helper}</p>
    </Card>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-2.5 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
      <div className="space-y-1">
        {eyebrow ? <p className="text-[12px] font-semibold uppercase tracking-[0.28em] text-[color:var(--accent)]">{eyebrow}</p> : null}
        <h2 className="text-[1.28rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50 md:text-[1.45rem]">{title}</h2>
        {description ? <p className="max-w-3xl text-[12px] leading-5 text-[color:var(--text-muted)]">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Button({
  children,
  className,
  variant = "primary",
  type = "button",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  const variants = {
    primary:
      "border border-transparent bg-[linear-gradient(135deg,#0f4c81,#1098ad)] text-white shadow-[0_22px_40px_-24px_rgba(15,76,129,0.65)] hover:shadow-[0_28px_48px_-24px_rgba(16,152,173,0.52)] dark:bg-[linear-gradient(135deg,#126e82,#6fe6ee)] dark:text-slate-950",
    secondary:
      "border border-[color:var(--surface-border-strong)] bg-[#151d28] text-white shadow-[0_20px_36px_-24px_rgba(15,23,32,0.56)] hover:bg-[#111925] dark:bg-[#f2f4f6] dark:text-slate-950 dark:hover:bg-white",
    ghost:
      "border border-[color:var(--surface-border)] bg-[var(--surface-strong)] text-slate-700 shadow-[0_14px_30px_-24px_rgba(15,23,32,0.28)] hover:border-[color:var(--accent)] hover:bg-white hover:text-slate-950 dark:bg-[var(--surface-muted)] dark:text-slate-200 dark:hover:border-[color:var(--accent)] dark:hover:bg-[rgba(27,35,46,0.96)] dark:hover:text-white",
    danger:
      "border border-transparent bg-[linear-gradient(135deg,#c41c44,#ef4444)] text-white shadow-[0_20px_38px_-24px_rgba(185,28,62,0.55)] hover:shadow-[0_26px_44px_-24px_rgba(239,68,68,0.52)]",
  };

  return (
    <button
      type={type}
      className={cn(
        "inline-flex min-w-0 cursor-pointer select-none items-center justify-center rounded-[10px] px-3 py-2 text-center text-[12px] font-medium leading-5",
        "transition-[transform,background-color,border-color,color,box-shadow,opacity] duration-200 ease-out will-change-transform active:translate-y-0 active:scale-[0.985]",
        "disabled:cursor-not-allowed disabled:opacity-60",
        variants[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const inputId = props.id ?? (typeof props.name === "string" ? props.name : undefined);
  return (
    <input
      {...props}
      id={inputId}
      className={cn(
        "h-9 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 text-[12px] text-slate-900 outline-none ring-0 transition placeholder:text-slate-400 focus:border-[color:var(--accent)] focus:bg-white",
        "min-w-0",
        "dark:border-[color:var(--surface-border)] dark:bg-[var(--surface-muted)] dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-[color:var(--accent)] dark:focus:bg-[rgba(21,28,38,0.98)]",
        props.className,
      )}
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const textareaId = props.id ?? (typeof props.name === "string" ? props.name : undefined);
  return (
    <textarea
      {...props}
      id={textareaId}
      className={cn(
        "min-h-[96px] rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[12px] leading-5 text-slate-900 outline-none ring-0 transition placeholder:text-slate-400 focus:border-[color:var(--accent)] focus:bg-white",
        "min-w-0 resize-y",
        "dark:border-[color:var(--surface-border)] dark:bg-[var(--surface-muted)] dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-[color:var(--accent)] dark:focus:bg-[rgba(21,28,38,0.98)]",
        props.className,
      )}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const selectId = props.id ?? (typeof props.name === "string" ? props.name : undefined);
  return (
    <select
      {...props}
      id={selectId}
      className={cn(
        "h-9 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 text-[12px] text-slate-900 outline-none transition focus:border-[color:var(--accent)] focus:bg-white",
        "min-w-0",
        "dark:border-[color:var(--surface-border)] dark:bg-[var(--surface-muted)] dark:text-slate-100 dark:focus:border-[color:var(--accent)] dark:focus:bg-[rgba(21,28,38,0.98)]",
        props.className,
      )}
    />
  );
}

export function StatusBadge({ status, label }: { status?: string; label: string }) {
  const tone = statusTone(status);
  const tones = {
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
    rose: "bg-rose-50 text-rose-700 ring-rose-200",
    slate: "bg-slate-100 text-slate-600 ring-slate-200",
  };
  return (
    <span
      className={cn(
        "inline-flex max-w-full min-w-0 items-center justify-center rounded-full px-2.5 py-1 text-center text-[10px] font-semibold uppercase tracking-[0.14em] leading-4 ring-1 ring-inset",
        tones[tone],
      )}
    >
      <span className="break-words">{label}</span>
    </span>
  );
}

export function DetailPanel({
  title,
  subtitle,
  actions,
  onClose,
  children,
  variant = "sticky",
  className,
  bodyClassName,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  onClose?: () => void;
  children: ReactNode;
  variant?: "sticky" | "overlay";
  className?: string;
  bodyClassName?: string;
}) {
  const header = (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 space-y-1">
        <h3 className="break-words text-lg font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{title}</h3>
        {subtitle ? <p className="break-words text-[13px] leading-5 text-[color:var(--text-muted)]">{subtitle}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {actions}
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-[14px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] text-slate-500 transition-[transform,background-color,border-color,color,box-shadow] duration-200 ease-out hover:border-[color:var(--accent)] hover:text-slate-950 hover:shadow-[0_16px_28px_-22px_rgba(15,76,129,0.3)] active:translate-y-0 active:scale-[0.985] dark:bg-[var(--surface-muted)] dark:text-slate-300 dark:hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
      </div>
    </div>
  );

  if (variant === "overlay") {
    return (
      <div className="fixed inset-0 z-50">
        <div className="absolute inset-0 bg-slate-950/48 backdrop-blur-sm" onClick={onClose} />
        <div className="absolute inset-0 flex items-start justify-center px-3 py-4 md:px-6 md:py-6">
          <Card className={cn("overlay-scrollbar soft-enter flex max-h-[calc(100vh-2rem)] w-full max-w-[1080px] flex-col overflow-hidden p-0", className)}>
            <div className="border-b border-[color:var(--surface-border)] px-4 py-3">{header}</div>
            <div className={cn("flex-1 overflow-auto px-4 py-3", bodyClassName)}>{children}</div>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <Card className={cn("sticky top-[4.5rem] space-y-3", className)}>
      {header}
      <div className={bodyClassName}>{children}</div>
    </Card>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <Card className="flex min-h-44 flex-col items-center justify-center gap-2 text-center">
      <h3 className="text-lg font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">{title}</h3>
      <p className="max-w-sm text-sm leading-6 text-[color:var(--text-muted)]">{description}</p>
    </Card>
  );
}

export function NoticeBanner({
  tone = "info",
  children,
}: {
  tone?: "info" | "success" | "warning" | "error";
  children: ReactNode;
}) {
  const tones = {
    info: "border-[rgba(16,152,173,0.24)] bg-[rgba(16,152,173,0.08)] text-[#0f4c81] dark:border-[rgba(111,230,238,0.22)] dark:bg-[rgba(111,230,238,0.08)] dark:text-[#b8f9ff]",
    success: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-200",
    warning: "border-[rgba(255,180,91,0.28)] bg-[rgba(255,180,91,0.12)] text-[#8a5209] dark:border-[rgba(255,195,109,0.28)] dark:bg-[rgba(255,195,109,0.1)] dark:text-[#ffd7a0]",
    error: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/25 dark:bg-rose-500/10 dark:text-rose-200",
  };

  return <div className={cn("rounded-[22px] border px-4 py-3 text-sm leading-6", tones[tone])}>{children}</div>;
}
