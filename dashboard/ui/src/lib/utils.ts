import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatRub(value: number | string | null | undefined) {
  const numeric = Number(value ?? 0);
  if (Number.isNaN(numeric)) {
    return "0 ₽";
  }
  return `${new Intl.NumberFormat("ru-RU").format(numeric)} ₽`;
}

export function statusTone(status: string | undefined) {
  switch (status) {
    case "active":
    case "trial":
    case "sync_complete":
    case "paid_active":
    case "trial_active":
    case "healthy":
    case "online":
    case "confirmed":
    case "posted":
      return "emerald";
    case "maintenance":
    case "degradation":
    case "awaiting_payment":
    case "repair_needed":
    case "sync_error":
    case "warning":
    case "awaiting_admin_review":
    case "awaiting_user_payment":
    case "disputed":
    case "draft":
      return "amber";
    case "critical":
    case "down":
    case "offline":
    case "rejected":
    case "error":
    case "blocked":
    case "cancelled":
    case "inactive":
    case "no_access":
    case "expired":
      return "rose";
    default:
      return "slate";
  }
}
