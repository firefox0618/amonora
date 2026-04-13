"use client";

import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, BadgeRussianRuble, Server, ShieldAlert, Users, Wallet } from "lucide-react";
import { Button, Card, MetricCard, NoticeBanner, SectionHeading, StatusBadge } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useOverview } from "@/hooks/use-dashboard";
import { apiPost } from "@/lib/api";
import { describeRepairResult } from "@/lib/repair-feedback";
import { useToasts } from "@/components/toast-center";
import { UserVpnRepairActionResult } from "@/lib/types";
import { formatRub } from "@/lib/utils";

function formatAuditAction(label?: string | null, action?: string | null) {
  return String(label || action || "Системное действие");
}

function attentionTone(priority?: string) {
  if (priority === "high") return "warning";
  if (priority === "medium") return "pending";
  return "healthy";
}

function confirmAction(message: string): boolean {
  if (typeof window === "undefined") return true;
  return window.confirm(message);
}

export default function OverviewPage() {
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const query = useOverview();

  const repairMutation = useMutation({
    mutationFn: (userId: number) => apiPost<UserVpnRepairActionResult>(`/users/${userId}/sync`),
    onSuccess: async (data, userId) => {
      const feedback = describeRepairResult(data);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
        queryClient.invalidateQueries({ queryKey: ["users"] }),
        queryClient.invalidateQueries({ queryKey: ["user-detail", userId] }),
      ]);
      pushToast({
        title: feedback.title,
        description: feedback.description,
        tone: feedback.tone,
      });
    },
    onError: (error: Error) => {
      pushToast({ title: "Синхронизация не выполнена", description: error.message, tone: "error" });
    },
  });

  if (query.isLoading) return <PageLoader />;
  if (query.error || !query.data) return <PageError message={query.error?.message || "Нет данных панели"} />;

  const { kpis, user_distribution, rail, attention, system_alerts } = query.data;
  const metricCards = [
    {
      label: "Пользователи",
      value: `${kpis.total_users}/${kpis.paid_users ?? 0}`,
      helper: "всего / платные",
      icon: Users,
    },
    {
      label: "Устройства",
      value: `${kpis.devices_total ?? 0}/${kpis.active_connections}`,
      helper: "всего / активные",
      icon: ShieldAlert,
    },
    {
      label: "Выручка",
      value: `${formatRub(kpis.monthly_revenue)}/${formatRub(kpis.daily_revenue ?? 0)}`,
      helper: "30 дней / сегодня",
      icon: BadgeRussianRuble,
    },
    {
      label: "Прирост",
      value: `${kpis.new_users ?? 0}/${kpis.new_users_24h ?? 0}`,
      helper: "7 дней / сутки",
      icon: Server,
    },
  ];

  const attentionItems = [
    ...(attention.repair_needed_users || []).slice(0, 4).map((item) => ({
      key: `repair-${item.user_id}`,
      title: item.username,
      text: item.reason_label || "Нужна ручная проверка доступа",
      href: item.href,
      priority: item.priority,
      syncUserId: item.can_repair ? item.user_id : null,
      badge: "Sync",
    })),
    ...(system_alerts.payments?.oldest_pending_manual_payments || []).slice(0, 3).map((item) => ({
      key: `payment-${item.record_id}`,
      title: item.username,
      text: `Платёж ждёт проверки ${item.age_hours} ч`,
      href: item.href,
      priority: item.priority,
      syncUserId: null,
      badge: "Платёж",
    })),
    ...(system_alerts.support?.oldest_open_tickets || []).slice(0, 3).map((item) => ({
      key: `support-${item.user_id}`,
      title: item.username,
      text: `Обращение открыто ${item.age_hours ?? 0} ч`,
      href: item.href,
      priority: item.priority,
      syncUserId: null,
      badge: "Support",
    })),
    ...(system_alerts.nodes?.items || []).slice(0, 3).map((item) => ({
      key: `node-${item.server_id}`,
      title: item.name,
      text: `${item.status_label} · CPU ${item.cpu_percent}% · RAM ${item.memory_used_percent}%`,
      href: item.href,
      priority: item.status_state === "down" ? "high" : "medium",
      syncUserId: null,
      badge: "Нода",
    })),
  ].slice(0, 8);

  return (
    <div className="space-y-4">
      <SectionHeading title="Панель управления" description="Пользователи, устройства, выручка и внимание." />

      <div className="grid gap-3 xl:grid-cols-4">
        {metricCards.map((item) => {
          const Icon = item.icon;
          return (
            <MetricCard
              key={item.label}
              label={item.label}
              value={
                <div className="flex items-center justify-between gap-3">
                  <span>{item.value}</span>
                  <span className="flex h-7 w-7 items-center justify-center rounded-[9px] bg-[rgba(96,123,137,0.12)] text-[color:var(--accent)]">
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                </div>
              }
              helper={item.helper}
            />
          );
        })}
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-[14px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Срез тарифа</h3>
            <span className="text-[13px] text-[color:var(--text-muted)]">Сумма = {kpis.total_users}</span>
          </div>
          <div className="grid gap-2">
            {(user_distribution.plans || []).map((plan) => (
              <div key={`${plan.label}-${plan.count}`} className="flex items-center justify-between rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2">
                <span className="truncate text-[13px] text-slate-700 dark:text-slate-200">{plan.label}</span>
                <span className="text-[15px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">{plan.count}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-[14px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Последние платежи</h3>
            <Link href="/payments" className="text-[13px] font-medium text-[color:var(--accent)]">
              Все платежи
            </Link>
          </div>
          <div className="space-y-2">
            {(rail.recent_payments || []).length ? (
              rail.recent_payments.slice(0, 5).map((payment) => (
                <Link
                  key={payment.id}
                  href={`/payments?record_id=${payment.id}`}
                  className="flex items-center justify-between gap-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[13px]"
                >
                  <div className="min-w-0">
                    <div className="truncate font-semibold text-slate-950 dark:text-slate-50">{payment.username}</div>
                    <div className="truncate text-[13px] text-[color:var(--text-muted)]">{payment.created_at}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatRub(payment.amount)}</span>
                    <StatusBadge status={payment.payment_status} label={payment.payment_status_label} />
                  </div>
                </Link>
              ))
            ) : (
              <NoticeBanner tone="info">Платежей пока нет.</NoticeBanner>
            )}
          </div>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-[14px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Что требует внимания</h3>
            <div className="flex items-center gap-2 text-[13px] text-[color:var(--text-muted)]">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>{attentionItems.length}</span>
            </div>
          </div>
          <div className="space-y-2">
            {attentionItems.length ? (
              attentionItems.map((item) => (
                <div key={item.key} className="flex items-center justify-between gap-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2">
                  <Link href={item.href} className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                    <div className="truncate text-[13px] font-semibold text-slate-950 dark:text-slate-50">{item.title}</div>
                      <StatusBadge status={attentionTone(item.priority)} label={item.badge} />
                    </div>
                    <div className="truncate text-[13px] text-[color:var(--text-muted)]">{item.text}</div>
                  </Link>
                  {item.syncUserId ? (
                    <Button
                      variant="ghost"
                      disabled={repairMutation.isPending}
                      onClick={() => {
                        if (!confirmAction(`Запустить синхронизацию доступа для ${item.title}?`)) {
                          return;
                        }
                        repairMutation.mutate(item.syncUserId as number);
                      }}
                    >
                      Sync
                    </Button>
                  ) : (
                    <Link href={item.href} className="inline-flex items-center text-[13px] font-medium text-[color:var(--accent)]">
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  )}
                </div>
              ))
            ) : (
              <NoticeBanner tone="success">Критичных проблем в текущем срезе нет.</NoticeBanner>
            )}
          </div>
        </Card>

        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-[14px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Последние действия админов</h3>
            <Link href="/audit" className="text-[13px] font-medium text-[color:var(--accent)]">
              Весь аудит
            </Link>
          </div>
          <div className="space-y-2">
            {(rail.recent_activity || []).length ? (
              rail.recent_activity.slice(0, 8).map((item) => (
                <div key={item.id} className="rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="truncate text-[13px] font-semibold text-slate-950 dark:text-slate-50">
                      {formatAuditAction(item.action_label, item.action)}
                    </div>
                    <div className="text-[12px] text-[color:var(--text-muted)]">{item.created_at}</div>
                  </div>
                  <div className="mt-1 text-[13px] text-[color:var(--text-muted)]">
                    {item.admin_name}
                    {item.target_id ? ` · ${item.target_id}` : ""}
                    {item.details_text ? ` · ${item.details_text}` : ""}
                  </div>
                </div>
              ))
            ) : (
              <NoticeBanner tone="info">Действий пока нет.</NoticeBanner>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
