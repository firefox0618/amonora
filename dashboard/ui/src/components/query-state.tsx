"use client";

import { Loader2 } from "lucide-react";
import { Card } from "@/components/ui";

export function PageLoader({ label = "Загружаю данные..." }: { label?: string }) {
  return (
    <Card className="control-grid flex min-h-72 flex-col items-center justify-center gap-4 text-center text-[color:var(--text-muted)]">
      <div className="flex h-14 w-14 items-center justify-center rounded-full border border-[color:var(--surface-border)] bg-[var(--surface-strong)]">
        <Loader2 className="h-5 w-5 animate-spin text-[color:var(--accent)]" />
      </div>
      <span className="text-sm font-medium">{label}</span>
    </Card>
  );
}

export function PageError({ message }: { message: string }) {
  return (
    <Card className="flex min-h-72 flex-col items-center justify-center gap-3 text-center">
      <h3 className="text-lg font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Не удалось загрузить данные</h3>
      <p className="max-w-md text-sm leading-6 text-[color:var(--text-muted)]">{message}</p>
    </Card>
  );
}
