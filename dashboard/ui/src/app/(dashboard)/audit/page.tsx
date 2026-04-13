"use client";

import { useMemo, useState } from "react";
import { Card, EmptyState, Input, MetricCard, SectionHeading, Select } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useAudit } from "@/hooks/use-dashboard";

const TARGET_LABELS: Record<string, string> = {
  user: "Пользователь",
  payment_record: "Платёж",
  support_ticket: "Обращение",
  server: "Нода",
  dashboard_admin: "Администратор",
  finance_entry: "Финансы",
  role_permission: "Разрешение роли",
  env: "Окружение",
  traffic: "Трафик",
};

const ACTION_LABEL_OVERRIDES: Record<string, string> = {
  server_watchdog_recovered: "восстановлен",
  server_watchdog_down: "оффлайн",
  server_watchdog_overloaded: "Нода перегружена, нужно снять часть нагрузки",
  login_code_requested: "Выдача кода",
  request_login_code_v2: "Выдача кода",
  delete_user: "удаление пользователя",
  logout_v2: "выход",
  extend_subscription: "продление",
  unblock_user: "разблокировка доступа",
  block_user: "блокировка доступа",
  remove_user_tariff: "Снял тариф пользователя",
};

function formatActionLabel(action?: string | null, actionLabel?: string | null) {
  if (action && ACTION_LABEL_OVERRIDES[action]) return ACTION_LABEL_OVERRIDES[action];
  return String(actionLabel || action || "Системное событие").replaceAll("_", " ");
}

function formatTargetLabel(target?: string | null) {
  return TARGET_LABELS[String(target || "")] || String(target || "Система").replaceAll("_", " ");
}

export default function AuditPage() {
  const auditQuery = useAudit();
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState("all");
  const [targetFilter, setTargetFilter] = useState("all");

  const items = auditQuery.data?.items ?? [];
  const actionOptions = useMemo(() => {
    const map = new Map<string, string>();
    items.forEach((item) => {
      if (item.action) {
        map.set(item.action, formatActionLabel(item.action, item.action_label));
      }
    });
    return Array.from(map.entries()).sort((left, right) => left[1].localeCompare(right[1], "ru"));
  }, [items]);
  const targetOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.target_type).filter(Boolean) as string[])).sort(),
    [items],
  );
  const filteredItems = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return items.filter((item) => {
      if (actionFilter !== "all" && item.action !== actionFilter) return false;
      if (targetFilter !== "all" && item.target_type !== targetFilter) return false;
      if (!needle) return true;
      const haystack = [
        item.admin_name,
        item.action_label,
        item.action,
        item.target_type,
        item.target_id,
        item.details_text,
        item.raw_details_text,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [actionFilter, items, search, targetFilter]);

  if (auditQuery.isLoading) return <PageLoader />;
  if (auditQuery.error || !auditQuery.data) {
    return <PageError message={auditQuery.error?.message || "Не удалось загрузить журнал"} />;
  }

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Аудит"
        description="Журнал действий команды."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input
              id="audit-search"
              name="auditSearch"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск"
              className="w-full md:w-56"
            />
            <Select id="audit-action-filter" name="auditActionFilter" value={actionFilter} onChange={(event) => setActionFilter(event.target.value)}>
              <option value="all">Все действия</option>
              {actionOptions.map(([action, label]) => (
                <option key={action} value={action}>
                  {label}
                </option>
              ))}
            </Select>
            <Select id="audit-target-filter" name="auditTargetFilter" value={targetFilter} onChange={(event) => setTargetFilter(event.target.value)}>
              <option value="all">Все цели</option>
              {targetOptions.map((target) => (
                <option key={target} value={target}>
                  {formatTargetLabel(target)}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      <div className="grid gap-3 xl:grid-cols-5">
        <MetricCard label="Событий" value={filteredItems.length} helper={`Из ${auditQuery.data.summary.total}`} />
        <MetricCard label="Действий" value={auditQuery.data.summary.unique_actions} helper="Уникальных типов" />
        <MetricCard label="Админов" value={auditQuery.data.summary.active_admins} helper="В текущем срезе" />
        <MetricCard label="Целей" value={auditQuery.data.summary.target_types} helper="Типов объектов" />
        <MetricCard label="Последнее" value={auditQuery.data.summary.latest_event_at} helper="Свежесть журнала" />
      </div>

      <div className="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)]">
        <div className="space-y-3">
          <Card>
            <div className="mb-3 text-[13px] font-semibold text-slate-950 dark:text-slate-50">Частые действия</div>
            <div className="space-y-2">
              {auditQuery.data.top_actions.length ? (
                auditQuery.data.top_actions.map((row) => (
                  <div key={row.action} className="flex items-center justify-between gap-3 rounded-[12px] border border-slate-200 bg-slate-50/90 px-3 py-2 text-[12px] dark:border-slate-800 dark:bg-slate-900/70">
                    <span className="min-w-0 truncate text-slate-700 dark:text-slate-300">{formatActionLabel(row.action)}</span>
                    <span className="shrink-0 font-semibold text-slate-950 dark:text-slate-50">{row.count}</span>
                  </div>
                ))
              ) : (
                <div className="rounded-[12px] border border-dashed border-slate-200 px-3 py-4 text-[12px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  Нет данных.
                </div>
              )}
            </div>
          </Card>

          <Card>
            <div className="mb-3 text-[13px] font-semibold text-slate-950 dark:text-slate-50">Активные админы</div>
            <div className="space-y-2">
              {auditQuery.data.top_admins.length ? (
                auditQuery.data.top_admins.map((row) => (
                  <div key={row.name} className="flex items-center justify-between gap-3 rounded-[12px] border border-slate-200 bg-slate-50/90 px-3 py-2 text-[12px] dark:border-slate-800 dark:bg-slate-900/70">
                    <span className="min-w-0 truncate text-slate-700 dark:text-slate-300">{row.name}</span>
                    <span className="shrink-0 font-semibold text-slate-950 dark:text-slate-50">{row.count}</span>
                  </div>
                ))
              ) : (
                <div className="rounded-[12px] border border-dashed border-slate-200 px-3 py-4 text-[12px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  Нет данных.
                </div>
              )}
            </div>
          </Card>
        </div>

        <Card className="overflow-hidden p-0">
          <div className="grid grid-cols-[0.9fr_0.9fr_1fr_0.9fr_1.3fr] gap-3 border-b border-[color:var(--surface-border)] px-4 py-2 text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
            <span>Дата</span>
            <span>Админ</span>
            <span>Действие</span>
            <span>Цель</span>
            <span>Детали</span>
          </div>
          {filteredItems.length ? (
            <div>
              {filteredItems.map((item) => (
                <div key={item.id} className="grid grid-cols-[0.9fr_0.9fr_1fr_0.9fr_1.3fr] gap-3 border-b border-[color:var(--surface-border)] px-4 py-2.5 text-[13px]">
                  <div className="text-[13px] text-[color:var(--text-muted)]">{item.created_at}</div>
                  <div className="truncate font-medium text-slate-950 dark:text-slate-50">{item.admin_name}</div>
                  <div className="truncate text-slate-950 dark:text-slate-50">{formatActionLabel(item.action, item.action_label)}</div>
                  <div className="truncate text-[color:var(--text-muted)]">
                    {formatTargetLabel(item.target_type)}
                    {item.target_id ? ` · ${item.target_id}` : ""}
                  </div>
                  <div className="truncate text-[color:var(--text-muted)]" title={item.raw_details_text || item.details_text || undefined}>
                    {item.details_text || "—"}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-4">
              <EmptyState title="Совпадений нет" description="Сбрось фильтры или измени запрос." />
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
