"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, MouseEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Card, DetailPanel, EmptyState, Input, MetricCard, NoticeBanner, SectionHeading, Select, StatusBadge } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useSession, useUserDetail, useUsers } from "@/hooks/use-dashboard";
import { apiGet, apiPost } from "@/lib/api";
import { describeRepairResult } from "@/lib/repair-feedback";
import { UserDetailPayload, UserDeviceStatusPayload, UserVpnRepairActionResult } from "@/lib/types";
import { useToasts } from "@/components/toast-center";

type DeviceStatusView = {
  status_key?: string | null;
  status_label?: string | null;
  status_reason?: string | null;
  status_checked_at?: string | null;
};

function mergeDeviceStatus(
  device: UserDetailPayload["devices"][number],
  override?: UserDeviceStatusPayload,
): DeviceStatusView {
  return {
    status_key: override?.status_key ?? device.status_key ?? "unknown",
    status_label: override?.status_label ?? device.status_label ?? "Не проверяли",
    status_reason: override?.status_reason ?? device.status_reason ?? "Нажмите «Статус», чтобы проверить ключ",
    status_checked_at: override?.status_checked_at ?? device.status_checked_at ?? null,
  };
}

function deviceStatusTone(statusKey?: string | null) {
  if (statusKey === "healthy" || statusKey === "online" || statusKey === "offline") {
    return "text-emerald-700 dark:text-emerald-300";
  }
  if (statusKey === "broken") {
    return "text-rose-700 dark:text-rose-300";
  }
  return "text-slate-600 dark:text-slate-300";
}

export default function UsersPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const session = useSession();
  const [searchInput, setSearchInput] = useState(searchParams.get("q") || "");
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || "all");
  const [planFilter, setPlanFilter] = useState(searchParams.get("plan") || "all");
  const [issueFilter, setIssueFilter] = useState(searchParams.get("issue") || "all");
  const [page, setPage] = useState(Math.max(Number(searchParams.get("page") || 1) || 1, 1));
  const [selectedUserId, setSelectedUserId] = useState<number | undefined>(
    searchParams.get("user_id") ? Number(searchParams.get("user_id")) : undefined,
  );
  const [extendDays, setExtendDays] = useState("30");
  const [protocolOverrides, setProtocolOverrides] = useState<Record<number, string>>({});
  const [deviceStatusOverrides, setDeviceStatusOverrides] = useState<Record<number, UserDeviceStatusPayload>>({});
  const [statusLoadingDeviceId, setStatusLoadingDeviceId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [deviceForm, setDeviceForm] = useState({
    device_name: "",
    device_type: "desktop",
    protocol: "vless",
    country_code: "de",
  });
  useEffect(() => {
    setSearchInput(searchParams.get("q") || "");
    setStatusFilter(searchParams.get("status") || "all");
    setPlanFilter(searchParams.get("plan") || "all");
    setIssueFilter(searchParams.get("issue") || "all");
    setPage(Math.max(Number(searchParams.get("page") || 1) || 1, 1));
    setSelectedUserId(searchParams.get("user_id") ? Number(searchParams.get("user_id")) : undefined);
  }, [searchParams]);

  useEffect(() => {
    setDeviceStatusOverrides({});
    setStatusLoadingDeviceId(null);
  }, [selectedUserId]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const nextQuery = searchInput.trim();
      const currentQuery = searchParams.get("q") || "";
      if (nextQuery === currentQuery) {
        return;
      }
      const params = new URLSearchParams(searchParams.toString());
      if (nextQuery) params.set("q", nextQuery);
      else params.delete("q");
      params.set("page", "1");
      router.replace(`/users${params.toString() ? `?${params.toString()}` : ""}`, { scroll: false });
    }, 250);
    return () => window.clearTimeout(handle);
  }, [router, searchInput, searchParams]);

  const usersQuery = useUsers({
    query: searchParams.get("q") || "",
    statusFilter,
    planFilter,
    issueFilter,
    page,
    pageSize: 100,
  });
  const detailQuery = useUserDetail(selectedUserId);
  const permissions = session.data?.admin.permissions ?? {};

  const detail = detailQuery.data
    ? {
        ...detailQuery.data,
        vpn_repair_state: detailQuery.data.vpn_repair_state ?? {
          repair_needed: false,
          reason: null,
          reason_label: null,
          source: null,
          source_label: null,
          marked_at: null,
        },
        repair_action: detailQuery.data.repair_action ?? {
          can_repair: false,
          blocked_reason: "manual_repair_no_access",
        },
        sync_action: detailQuery.data.sync_action ?? {
          can_sync: false,
          blocked_reason: "manual_repair_no_access",
        },
        deep_repair_action: detailQuery.data.deep_repair_action ?? {
          can_deep_repair: false,
          blocked_reason: "manual_repair_no_access",
        },
        devices: detailQuery.data.devices ?? [],
        payments: detailQuery.data.payments ?? [],
        balance_history: detailQuery.data.balance_history ?? [],
      }
    : null;

  const currentProtocol =
    selectedUserId && detail
      ? protocolOverrides[selectedUserId] ?? detail.user.preferred_protocol ?? "vless"
      : "vless";
  const activeUserId = detail?.user.id ?? selectedUserId;

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["users"] }),
      queryClient.invalidateQueries({ queryKey: ["user-detail", selectedUserId] }),
      queryClient.invalidateQueries({ queryKey: ["overview"] }),
      queryClient.invalidateQueries({ queryKey: ["traffic"] }),
      queryClient.invalidateQueries({ queryKey: ["servers"] }),
      queryClient.invalidateQueries({ queryKey: ["payments"] }),
    ]);
  };

  const resolveActionFeedback = (
    payload: UserDetailPayload | { deleted_user_id: number } | UserVpnRepairActionResult | unknown,
    fallbackSuccess: string,
    fallbackWarning: string,
  ) => {
    const actionResult =
      payload && typeof payload === "object" && "action_result" in (payload as Record<string, unknown>)
        ? ((payload as UserDetailPayload).action_result ?? null)
        : null;
    if (!actionResult) {
      return { message: fallbackSuccess, tone: "success" as const };
    }
    if (actionResult.sync_failed) {
      return { message: fallbackWarning, tone: "warning" as const };
    }
    return { message: fallbackSuccess, tone: "success" as const };
  };

  type UserActionResponse = UserDetailPayload | { deleted_user_id: number } | UserVpnRepairActionResult;

  const actionMutation = useMutation({
    mutationFn: async (config: { path: string; body?: unknown }) => apiPost<UserActionResponse>(config.path, config.body),
    onSuccess: async () => {
      setError("");
      await refreshAll();
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      pushToast({ title: "Действие не выполнено", description: mutationError.message, tone: "error" });
    },
  });

  const refreshUserCardMutation = useMutation({
    mutationFn: async (userId: number) => apiGet<UserDetailPayload>(`/users/${userId}?force=1`),
    onSuccess: async (payload, userId) => {
      queryClient.setQueryData(["user-detail", userId], payload);
      setDeviceStatusOverrides((prev) =>
        Object.fromEntries(
          Object.entries(prev).filter(([deviceId]) => payload.devices.some((device) => device.id === Number(deviceId))),
        ),
      );
      setError("");
      setNotice("Карточка пользователя обновлена.");
      pushToast({ title: "Карточка обновлена", description: payload.user.username, tone: "info" });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["users"] }),
        queryClient.invalidateQueries({ queryKey: ["overview"] }),
      ]);
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      pushToast({ title: "Не удалось обновить карточку", description: mutationError.message, tone: "error" });
    },
  });

  const deviceStatusMutation = useMutation({
    mutationFn: async ({ userId, deviceId }: { userId: number; deviceId: number }) =>
      apiPost<UserDeviceStatusPayload>(`/users/${userId}/devices/${deviceId}/status`),
    onSuccess: (payload, variables) => {
      setDeviceStatusOverrides((prev) => ({ ...prev, [variables.deviceId]: payload }));
      queryClient.setQueryData<UserDetailPayload | undefined>(["user-detail", variables.userId], (current) => {
        if (!current) return current;
        return {
          ...current,
          devices: current.devices.map((device) =>
            device.id === variables.deviceId
              ? {
                  ...device,
                  mode_label: payload.mode_label ?? device.mode_label,
                  status_key: payload.status_key ?? device.status_key,
                  status_label: payload.status_label ?? device.status_label,
                  status_reason: payload.status_reason ?? device.status_reason,
                  status_checked_at: payload.status_checked_at ?? device.status_checked_at,
                }
              : device,
          ),
        };
      });
      setError("");
      pushToast({
        title: "Статус устройства обновлён",
        description: payload.status_label || "Проверка завершена",
        tone: payload.status_key === "broken" ? "warning" : "success",
      });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      if (mutationError.message.includes("Устройство не найдено") && activeUserId) {
        queryClient.invalidateQueries({ queryKey: ["user-detail", activeUserId] }).catch(() => undefined);
      }
      pushToast({ title: "Не удалось проверить устройство", description: mutationError.message, tone: "error" });
    },
    onSettled: () => {
      setStatusLoadingDeviceId(null);
    },
  });

  const channelTone = (status?: string) => {
    if (status === "subscribed") return "text-emerald-700 dark:text-emerald-300";
    if (status === "not_subscribed") return "text-amber-700 dark:text-amber-300";
    return "text-slate-500 dark:text-slate-400";
  };

  const protocolLabel = (value: string) => {
    if (value === "trojan") return "Trojan + TLS";
    return "VLESS";
  };

  const formatAmount = (value: number) => `${new Intl.NumberFormat("ru-RU").format(value || 0)} ₽`;
  const copyToClipboard = async (value: string, title: string) => {
    try {
      await navigator.clipboard.writeText(value);
      pushToast({ title, description: value, tone: "success" });
    } catch (clipboardError) {
      pushToast({
        title: "Не удалось скопировать ссылку",
        description: clipboardError instanceof Error ? clipboardError.message : "Буфер обмена недоступен",
        tone: "error",
      });
    }
  };
  const deviceTechnicalRows = (device: UserDetailPayload["devices"][number]) =>
    [
      { label: "Источник", value: String(device.metadata.device_source_label || "") },
      { label: "Слот", value: device.metadata.slot_index ? String(device.metadata.slot_index) : "" },
      { label: "ОС", value: device.technical.os_label },
      { label: "Модель", value: device.technical.device_model },
      { label: "Версия", value: device.technical.os_version },
      { label: "MAC", value: device.technical.mac_address },
      { label: "Провайдер", value: device.technical.provider_label },
      { label: "Транспорт", value: device.technical.transport_label },
      { label: "Профиль", value: device.technical.connection_profile },
      { label: "Anti-sharing", value: `${device.technical.anti_sharing_scope_label} · ${device.technical.anti_sharing_limit_label}` },
      { label: "Soft-limit", value: device.technical.anti_sharing_soft_limit_label },
      { label: "Политика", value: device.technical.anti_sharing_policy_summary },
      { label: "IP history", value: device.technical.ip_history },
      { label: "Активность", value: device.technical.last_seen_at },
    ].filter((item) => item.value && item.value !== "—");

  const stopActionClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const confirmAction = (message: string) => {
    if (typeof window === "undefined") return true;
    return window.confirm(message);
  };

  const onRefreshUserCardClick = (event: MouseEvent<HTMLButtonElement>) => {
    stopActionClick(event);
    if (!selectedUserId) return;
    refreshUserCardMutation.mutate(selectedUserId);
  };

  const onDeviceSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!selectedUserId) return;
    if (!confirmAction(`Создать устройство «${deviceForm.device_name || "Новое устройство"}» в регионе ${deviceForm.country_code.toUpperCase()}?`)) {
      return;
    }
    actionMutation.mutate(
      {
        path: `/users/${selectedUserId}/devices`,
        body: deviceForm,
      },
      {
        onSuccess: async () => {
          setNotice("Устройство создано.");
          pushToast({ title: "Устройство добавлено", description: deviceForm.device_name, tone: "success" });
          setDeviceForm((prev) => ({ ...prev, device_name: "" }));
          await refreshAll();
        },
      },
    );
  };

  const onExtendSubmit = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedUserId) return;
    const parsedDays = Number.parseInt(extendDays, 10);
    const safeDays = Number.isFinite(parsedDays) && parsedDays > 0 ? parsedDays : 30;
    if (!confirmAction(`Продлить доступ пользователю на ${safeDays} дн.?`)) {
      return;
    }
    actionMutation.mutate(
      { path: `/users/${selectedUserId}/extend`, body: { days: safeDays } },
      {
        onSuccess: async (payload) => {
          const feedback = resolveActionFeedback(
            payload,
            `Подписка продлена на ${safeDays} дн.`,
            `Подписка продлена на ${safeDays} дн., но часть устройств требует проверки.`,
          );
          setError("");
          setNotice(feedback.message);
          pushToast({ title: "Подписка продлена", description: feedback.message, tone: feedback.tone });
          await refreshAll();
        },
      },
    );
  };

  const onSyncClick = (event: MouseEvent<HTMLButtonElement>) => {
    stopActionClick(event);
    if (!selectedUserId) return;
    if (!confirmAction("Запустить синхронизацию доступа для этого пользователя?")) {
      return;
    }
    actionMutation.mutate(
      { path: `/users/${selectedUserId}/sync` },
      {
        onSuccess: async (data) => {
          if (!("sync_failed" in data)) {
            await refreshAll();
            return;
          }
          const feedback = describeRepairResult(data);
          if (data.sync_failed) {
            setNotice("");
            setError(feedback.description);
          } else {
            setError("");
            setNotice(feedback.description);
          }
          pushToast({ title: feedback.title, description: feedback.description, tone: feedback.tone });
          await refreshAll();
        },
      },
    );
  };

  const onDeepRepairClick = (event: MouseEvent<HTMLButtonElement>) => {
    stopActionClick(event);
    if (!selectedUserId) return;
    if (!confirmAction("Запустить глубокий ремонт доступа для этого пользователя?")) {
      return;
    }
    actionMutation.mutate(
      { path: `/users/${selectedUserId}/deep-repair` },
      {
        onSuccess: async (data) => {
          if (!("sync_failed" in data)) {
            await refreshAll();
            return;
          }
          const feedback = describeRepairResult(data);
          if (data.sync_failed) {
            setNotice("");
            setError(feedback.description);
          } else {
            setError("");
            setNotice(feedback.description);
          }
          pushToast({
            title: data.sync_failed ? "Глубокий ремонт завершился с ошибками" : "Глубокий ремонт завершён",
            description: feedback.description,
            tone: data.sync_failed ? "warning" : "success",
          });
          await refreshAll();
        },
      },
    );
  };

  const updateRouteParams = (mutate: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(searchParams.toString());
    mutate(params);
    router.replace(`/users${params.toString() ? `?${params.toString()}` : ""}`, { scroll: false });
  };

  const applyQuickSlice = (slice: "all" | "active" | "paid" | "trial" | "expired" | "blocked" | "no_access") => {
    const next = {
      status: "all",
      plan: "all",
      issue: "all",
    };
    if (slice === "active") next.status = "active";
    if (slice === "paid") {
      next.status = "active";
      next.plan = "paid";
    }
    if (slice === "trial") next.status = "trial";
    if (slice === "expired") {
      next.status = "no_access";
      next.plan = "paid";
    }
    if (slice === "blocked") next.status = "blocked";
    if (slice === "no_access") next.status = "no_access";

    setStatusFilter(next.status);
    setPlanFilter(next.plan);
    setIssueFilter(next.issue);
    updateRouteParams((params) => {
      if (next.status !== "all") params.set("status", next.status);
      else params.delete("status");
      if (next.plan !== "all") params.set("plan", next.plan);
      else params.delete("plan");
      if (next.issue !== "all") params.set("issue", next.issue);
      else params.delete("issue");
      params.set("page", "1");
    });
  };

  const activeQuickSlice =
    statusFilter === "all" && planFilter === "all" && issueFilter === "all"
      ? "all"
      : statusFilter === "active" && planFilter === "all"
        ? "active"
        : statusFilter === "active" && planFilter === "paid"
          ? "paid"
          : statusFilter === "trial" && planFilter === "all"
            ? "trial"
            : statusFilter === "no_access" && planFilter === "paid"
              ? "expired"
              : statusFilter === "blocked" && planFilter === "all"
                ? "blocked"
                : statusFilter === "no_access" && planFilter === "all"
                  ? "no_access"
                  : "";

  if (usersQuery.isLoading) return <PageLoader />;
  if (usersQuery.error || !usersQuery.data) return <PageError message={usersQuery.error?.message || "Не удалось загрузить пользователей"} />;

  const latestPayments = detail?.payments ?? [];

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Пользователи"
        description="Поиск, фильтры и действия."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input
              id="users-search"
              name="usersSearch"
              value={searchInput}
              onChange={(event) => {
                setSearchInput(event.target.value);
              }}
              placeholder="ID, TG, ник, тариф"
              className="w-full md:w-56"
            />
            <Select id="users-status-filter" name="usersStatusFilter" value={statusFilter} onChange={(event) => {
              setStatusFilter(event.target.value);
              updateRouteParams((params) => {
                if (event.target.value !== "all") params.set("status", event.target.value);
                else params.delete("status");
                params.set("page", "1");
              });
            }}>
              <option value="all">Статус</option>
              <option value="active">Активен</option>
              <option value="trial">Пробный</option>
              <option value="no_access">Без доступа</option>
              <option value="awaiting_payment">Ждёт оплату</option>
              <option value="repair_needed">Требует ремонта</option>
              <option value="blocked">Заблокирован</option>
            </Select>
            <Select id="users-plan-filter" name="usersPlanFilter" value={planFilter} onChange={(event) => {
              setPlanFilter(event.target.value);
              updateRouteParams((params) => {
                if (event.target.value !== "all") params.set("plan", event.target.value);
                else params.delete("plan");
                params.set("page", "1");
              });
            }}>
              <option value="all">Тариф</option>
              <option value="trial">Пробный</option>
              <option value="paid">Платный</option>
              <option value="1m">1 месяц</option>
              <option value="3m">3 месяца</option>
              <option value="6m">6 месяцев</option>
              <option value="12m">12 месяцев</option>
              <option value="none">Без тарифа</option>
            </Select>
            <Select id="users-issue-filter" name="usersIssueFilter" value={issueFilter} onChange={(event) => {
              setIssueFilter(event.target.value);
              updateRouteParams((params) => {
                if (event.target.value !== "all") params.set("issue", event.target.value);
                else params.delete("issue");
                params.set("page", "1");
              });
            }}>
              <option value="all">Срез</option>
              <option value="repair">Требует ремонта</option>
              <option value="payment">Ждёт оплату</option>
              <option value="blocked">Заблокирован</option>
            </Select>
          </div>
        }
      />
      <Card className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant={activeQuickSlice === "all" ? "primary" : "ghost"} onClick={() => applyQuickSlice("all")}>
            Все
          </Button>
          <Button variant={activeQuickSlice === "active" ? "primary" : "ghost"} onClick={() => applyQuickSlice("active")}>
            Активные
          </Button>
          <Button variant={activeQuickSlice === "paid" ? "primary" : "ghost"} onClick={() => applyQuickSlice("paid")}>
            Paid
          </Button>
          <Button variant={activeQuickSlice === "trial" ? "primary" : "ghost"} onClick={() => applyQuickSlice("trial")}>
            Trial
          </Button>
          <Button variant={activeQuickSlice === "expired" ? "primary" : "ghost"} onClick={() => applyQuickSlice("expired")}>
            Expired
          </Button>
          <Button variant={activeQuickSlice === "blocked" ? "primary" : "ghost"} onClick={() => applyQuickSlice("blocked")}>
            Blocked
          </Button>
          <Button variant={activeQuickSlice === "no_access" ? "primary" : "ghost"} onClick={() => applyQuickSlice("no_access")}>
            Без доступа
          </Button>
        </div>
      </Card>

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}

      <div className="grid gap-3 xl:grid-cols-5">
        <MetricCard label="Всего" value={usersQuery.data.summary.total} helper="Пользователи в срезе" />
        <MetricCard label="Активные" value={usersQuery.data.summary.active} helper="Есть доступ" />
        <MetricCard label="Пробные" value={usersQuery.data.summary.trial || 0} helper="Trial сейчас" />
        <MetricCard label="На оплате" value={usersQuery.data.summary.waiting_payment || 0} helper="Ждут проверку" />
        <MetricCard label="Требуют внимания" value={(usersQuery.data.summary.needs_repair || 0) + usersQuery.data.summary.blocked} helper="Ремонт и блок" />
      </div>

      <Card className="overflow-hidden p-0">
        <div className="grid grid-cols-[0.45fr_1.35fr_0.9fr_0.7fr_0.8fr_0.95fr_0.75fr] gap-3 border-b border-[color:var(--surface-border)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          <span>№</span>
          <span>Пользователь</span>
          <span>Страны</span>
          <span>Устройства</span>
          <span>Канал</span>
          <span>Доступ до</span>
          <span>Статус</span>
        </div>
        <div className="divide-y divide-[color:var(--surface-border)]">
          {usersQuery.data.items.length ? (
            usersQuery.data.items.map((user) => (
              <button
                key={user.id}
                type="button"
                onClick={() => {
                  setSelectedUserId(user.id);
                  const params = new URLSearchParams(searchParams.toString());
                  params.set("user_id", String(user.id));
                  router.replace(`/users?${params.toString()}`, { scroll: false });
                }}
                className={`grid w-full cursor-pointer grid-cols-[0.45fr_1.35fr_0.9fr_0.7fr_0.8fr_0.95fr_0.75fr] gap-3 px-4 py-3 text-left transition hover:bg-white/35 dark:hover:bg-white/4 ${
                  selectedUserId === user.id ? "bg-white/40 dark:bg-white/4" : ""
                }`}
              >
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">{user.id}</div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-slate-950 dark:text-slate-50">{user.username}</div>
                  <div className="truncate text-[13px] text-[color:var(--text-muted)]">TG {user.telegram_id} · {user.plan}</div>
                </div>
                <div className="truncate text-[13px] text-[color:var(--text-muted)]">{user.countries_label || user.top_country}</div>
                <div className="text-[13px] text-slate-700 dark:text-slate-300">{user.devices}/{user.max_devices || 3}</div>
                <div className={`truncate text-[13px] font-medium ${channelTone(user.channel_subscription_status)}`}>
                  {user.channel_subscription_label || "Не проверено"}
                </div>
                <div className="text-[13px] text-[color:var(--text-muted)]">{user.access_expires_at}</div>
                <StatusBadge status={user.status_state} label={user.status_label} />
              </button>
            ))
          ) : (
            <div className="px-5 py-10">
              <EmptyState title="Совпадений нет" description="Смени фильтры или поисковый запрос." />
            </div>
          )}
        </div>
        <div className="flex flex-col gap-3 border-t border-[color:var(--surface-border)] px-4 py-3 md:flex-row md:items-center md:justify-between">
          <div className="text-[13px] text-[color:var(--text-muted)]">
            Показано {usersQuery.data.pagination?.from_item || 0}-{usersQuery.data.pagination?.to_item || 0} из {usersQuery.data.pagination?.total_items || usersQuery.data.summary.total}
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={!usersQuery.data.pagination?.has_prev}
              onClick={() =>
                updateRouteParams((params) => {
                  const previousPage = Math.max((usersQuery.data.pagination?.page || 1) - 1, 1);
                  params.set("page", String(previousPage));
                })
              }
            >
              Назад
            </Button>
            <div className="min-w-[120px] text-center text-[13px] text-[color:var(--text-muted)]">
              Страница {usersQuery.data.pagination?.page || 1} из {usersQuery.data.pagination?.total_pages || 1}
            </div>
            <Button
              type="button"
              variant="secondary"
              disabled={!usersQuery.data.pagination?.has_next}
              onClick={() =>
                updateRouteParams((params) => {
                  const nextPage = (usersQuery.data.pagination?.page || 1) + 1;
                  params.set("page", String(nextPage));
                })
              }
            >
              Дальше
            </Button>
          </div>
        </div>
      </Card>

      {selectedUserId && detail ? (
        <DetailPanel
          variant="overlay"
          className="max-w-[1040px]"
          bodyClassName="space-y-4"
          title={detail.user.username}
          subtitle={`Пользователь ${detail.user.id}`}
          onClose={() => {
            setSelectedUserId(undefined);
            const params = new URLSearchParams(searchParams.toString());
            params.delete("user_id");
            router.replace(`/users${params.toString() ? `?${params.toString()}` : ""}`, { scroll: false });
          }}
        >
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_300px]">
            <div className="space-y-4">
              <Card className="space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Ник</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.username}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Айди TG</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.telegram_id}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Баланс</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatAmount(detail.user.balance_rub || 0)}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Канал</div><div className={`mt-1 text-[13px] font-semibold ${channelTone(detail.user.channel_subscription_status)}`}>{detail.user.channel_subscription_label || "Не проверено"}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Статус</div><div className="mt-1"><StatusBadge status={detail.user.status_state} label={detail.user.status_label || detail.user.status} /></div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Тариф</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.plan_label}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Регистрация</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.created_at || "—"}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Активация подписки</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.subscription_started_at || "—"}</div></div>
                  <div>
                    <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">IP</div>
                    <div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.last_known_ip || "—"}</div>
                    {detail.user.last_known_ip_source_label ? (
                      <div className="mt-1 text-[13px] text-[color:var(--text-muted)]">{detail.user.last_known_ip_source_label}</div>
                    ) : null}
                  </div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Доступ до</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.access_expires_at}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Устройства</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.devices_count ?? detail.devices.length} / {detail.user.max_devices || 3}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Базовый лимит</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.base_device_limit || 3}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Доп. слоты</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.extra_device_slots_active || 0}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Слот до</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.next_device_slot_expires_at || "—"}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Платежи</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{detail.user.payments_count ?? detail.payment_counts.total}</div></div>
                </div>
                {detail.vpn_repair_state.repair_needed ? (
                  <div className="rounded-[10px] border border-amber-300/60 bg-amber-50/60 px-3 py-2 text-[13px] text-amber-900 dark:border-amber-700/50 dark:bg-amber-950/20 dark:text-amber-100">
                    Требует проверки: {detail.vpn_repair_state.reason_label || detail.vpn_repair_state.reason || "repair"}
                  </div>
                ) : null}
                <div className="rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface)] px-3 py-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Ссылка подписки</div>
                    {detail.user.subscription_link_url ? (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={(event) => {
                          stopActionClick(event);
                          void copyToClipboard(detail.user.subscription_link_url || "", "Ссылка подписки скопирована");
                        }}
                      >
                        Скопировать
                      </Button>
                    ) : null}
                  </div>
                  {detail.user.subscription_link_url ? (
                    <>
                      <div className="mt-2 break-all text-[13px] font-semibold text-slate-950 dark:text-slate-50">
                        {detail.user.subscription_link_url}
                      </div>
                      <div className="mt-1 text-[12px] text-[color:var(--text-muted)]">
                        {detail.user.subscription_link_last_feed_accessed_at
                          ? `Последний импорт/обновление: ${detail.user.subscription_link_last_feed_accessed_at}`
                          : detail.user.subscription_link_last_viewed_at
                            ? `Последний просмотр: ${detail.user.subscription_link_last_viewed_at}`
                            : "Ссылка активна и готова для копирования."}
                      </div>
                    </>
                  ) : (
                    <div className="mt-2 text-[13px] text-[color:var(--text-muted)]">
                      Ссылка пока не появилась. Нажмите «Обновить», чтобы заново загрузить карточку пользователя.
                    </div>
                  )}
                </div>
              </Card>

              <Card className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">История баланса</div>
                  <div className="text-[13px] text-[color:var(--text-muted)]">
                    Сейчас: {formatAmount(detail.user.balance_rub || 0)}
                  </div>
                </div>
                {detail.balance_history.length ? (
                  detail.balance_history.map((entry) => (
                    <div key={entry.id} className="rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[13px]">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-slate-950 dark:text-slate-50">{entry.reason_label}</div>
                          <div className="truncate text-[color:var(--text-muted)]">{entry.created_at}</div>
                          <div className="mt-1 text-[color:var(--text-muted)]">
                            Баланс: {formatAmount(entry.balance_before)} → {formatAmount(entry.balance_after)}
                          </div>
                        </div>
                        <div className={`shrink-0 font-semibold ${entry.direction === "credit" ? "text-emerald-700 dark:text-emerald-300" : entry.direction === "debit" ? "text-rose-700 dark:text-rose-300" : "text-amber-700 dark:text-amber-300"}`}>
                          {entry.direction === "credit" ? "+" : entry.direction === "debit" ? "-" : "±"}{formatAmount(entry.amount)}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-[13px] text-[color:var(--text-muted)]">История баланса пока пустая.</div>
                )}
              </Card>

              <Card className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">История платежей</div>
                  <div className="text-[13px] text-[color:var(--text-muted)]">Всего: {detail.payment_counts.total}</div>
                </div>
                {latestPayments.length ? (
                  latestPayments.map((payment) => (
                    <div key={payment.id} className="flex items-center justify-between gap-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[13px]">
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-slate-950 dark:text-slate-50">#{payment.id} · {payment.payment_method_label}</div>
                        <div className="truncate text-[color:var(--text-muted)]">{payment.created_at}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-950 dark:text-slate-50">{payment.amount} ₽</span>
                        <StatusBadge status={payment.payment_status} label={payment.payment_status_label} />
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-[13px] text-[color:var(--text-muted)]">Платежей пока нет.</div>
                )}
              </Card>

              <Card className="space-y-2">
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Устройства</div>
                {detail.devices.length ? (
                  detail.devices.map((device) => {
                    const technicalRows = deviceTechnicalRows(device);
                    const deviceStatus = mergeDeviceStatus(device, deviceStatusOverrides[device.id]);
                    const isStatusLoading = statusLoadingDeviceId === device.id && deviceStatusMutation.isPending;
                    const isSubscriptionDevice = Boolean(device.metadata.subscription_route);
                    const canManageDevice = device.metadata.can_manage !== false && !isSubscriptionDevice;
                    return (
                    <div key={device.id} className="flex items-start justify-between gap-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[13px]">
                      <div className="min-w-0 space-y-1.5">
                        <div className="truncate font-semibold text-slate-950 dark:text-slate-50">{device.metadata.device_name}</div>
                        <div className="truncate text-[color:var(--text-muted)]">
                          {protocolLabel(device.protocol)} · {device.metadata.country_name} · IP {device.technical.ip_address || device.metadata.ip_address || "—"}
                        </div>
                        <div className="truncate text-[13px] text-slate-700 dark:text-slate-300">
                          Режим: <span className="font-semibold text-slate-950 dark:text-slate-50">{device.mode_label || "—"}</span>
                        </div>
                        {device.metadata.device_source_label ? (
                          <div className="truncate text-[12px] text-[color:var(--text-muted)]">
                            Источник: {String(device.metadata.device_source_label)}
                          </div>
                        ) : null}
                        {device.technical.ip_source_label ? (
                          <div className="truncate text-[12px] text-[color:var(--text-muted)]">{device.technical.ip_source_label}</div>
                        ) : null}
                        <div className="rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface)] px-3 py-2">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-muted)]">Статус ключа</div>
                            <div className={`text-[13px] font-semibold ${deviceStatusTone(deviceStatus.status_key)}`}>
                              {deviceStatus.status_label || "Не проверяли"}
                            </div>
                          </div>
                          {deviceStatus.status_reason ? (
                            <div className="mt-1 text-[12px] text-[color:var(--text-muted)]">Причина: {deviceStatus.status_reason}</div>
                          ) : null}
                          {deviceStatus.status_checked_at ? (
                            <div className="mt-1 text-[12px] text-[color:var(--text-muted)]">Проверено: {deviceStatus.status_checked_at}</div>
                          ) : null}
                        </div>
                        {technicalRows.length ? (
                          <div className="flex flex-wrap gap-1.5 text-[12px]">
                            {technicalRows.map((item) => (
                              <div
                                key={`${device.id}-${item.label}`}
                                className="rounded-full border border-[color:var(--surface-border)] bg-[var(--surface)] px-2 py-1 text-[color:var(--text-muted)]"
                              >
                                <span className="font-semibold text-slate-950 dark:text-slate-50">{item.label}:</span> {item.value}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 flex-col gap-2">
                        {canManageDevice ? (
                          <>
                            <Button
                              type="button"
                              variant="secondary"
                              disabled={isStatusLoading}
                              onClick={(event) => {
                                stopActionClick(event);
                                if (!activeUserId) return;
                                setStatusLoadingDeviceId(device.id);
                                deviceStatusMutation.mutate({ userId: activeUserId, deviceId: device.id });
                              }}
                            >
                              {isStatusLoading ? "Проверяем..." : "Статус"}
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              onClick={(event) => {
                                stopActionClick(event);
                                if (!confirmAction(`Удалить устройство «${device.metadata.device_name}»?`)) {
                                  return;
                                }
                                actionMutation.mutate(
                                  { path: `/users/${detail.user.id}/devices/${device.id}/delete` },
                                  {
                                    onSuccess: async () => {
                                      setNotice(`Устройство ${device.metadata.device_name} удалено.`);
                                      pushToast({ title: "Устройство удалено", description: device.metadata.device_name, tone: "warning" });
                                      await refreshAll();
                                    },
                                  },
                                );
                              }}
                            >
                              Удалить
                            </Button>
                          </>
                        ) : (
                          <div className="max-w-[180px] rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface)] px-3 py-2 text-[12px] text-[color:var(--text-muted)]">
                            Это устройство пришло из единой ссылки и пока доступно только для просмотра.
                          </div>
                        )}
                      </div>
                    </div>
                    );
                  })
                ) : (
                  <div className="text-[13px] text-[color:var(--text-muted)]">Устройств пока нет.</div>
                )}
              </Card>
            </div>

            <div className="space-y-3">
              <Card className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Ссылка подписки</div>
                  {detail.user.subscription_link_url ? (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={(event) => {
                        stopActionClick(event);
                        void copyToClipboard(detail.user.subscription_link_url || "", "Ссылка подписки скопирована");
                      }}
                    >
                      Скопировать
                    </Button>
                  ) : null}
                </div>
                {detail.user.subscription_link_url ? (
                  <>
                    <div className="break-all text-[13px] font-semibold text-slate-950 dark:text-slate-50">
                      {detail.user.subscription_link_url}
                    </div>
                    {detail.user.subscription_link_last_feed_accessed_at ? (
                      <div className="text-[12px] text-[color:var(--text-muted)]">
                        Последний импорт/обновление: {detail.user.subscription_link_last_feed_accessed_at}
                      </div>
                    ) : detail.user.subscription_link_last_viewed_at ? (
                      <div className="text-[12px] text-[color:var(--text-muted)]">
                        Последний просмотр: {detail.user.subscription_link_last_viewed_at}
                      </div>
                    ) : (
                      <div className="text-[12px] text-[color:var(--text-muted)]">
                        Ссылка активна и готова для копирования.
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-[13px] text-[color:var(--text-muted)]">
                    Ссылка пока не появилась. Нажмите «Обновить», чтобы заново загрузить карточку пользователя.
                  </div>
                )}
              </Card>

              <Card className="space-y-2">
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Действия</div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onRefreshUserCardClick}
                  disabled={refreshUserCardMutation.isPending}
                  className="w-full"
                >
                  {refreshUserCardMutation.isPending ? "Обновляем..." : "Обновить"}
                </Button>
                <Button type="button" onClick={onSyncClick} disabled={actionMutation.isPending || !detail.sync_action?.can_sync} className="w-full">Синхронизировать</Button>
                <Button type="button" variant="secondary" onClick={onDeepRepairClick} disabled={actionMutation.isPending || !permissions.can_run_deep_repair || !detail.deep_repair_action?.can_deep_repair} className="w-full">Глубокий ремонт</Button>
                <Input id="user-extend-days" name="extendDays" value={extendDays} onChange={(event) => setExtendDays(event.target.value)} placeholder="Дней" inputMode="numeric" pattern="[0-9]*" />
                <Button type="button" onClick={onExtendSubmit} disabled={actionMutation.isPending} className="w-full">Продлить доступ</Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  onClick={(event) => {
                    stopActionClick(event);
                    if (!confirmAction("Убрать тариф и отключить доступ пользователю?")) {
                      return;
                    }
                    actionMutation.mutate(
                      { path: `/users/${detail.user.id}/clear-access`, body: { remove_devices: false } },
                      {
                        onSuccess: async (payload) => {
                          const feedback = resolveActionFeedback(payload, "Тариф снят и доступ отключён.", "Тариф снят, но часть устройств требует проверки.");
                          setError("");
                          setNotice(feedback.message);
                          pushToast({ title: "Доступ снят", description: feedback.message, tone: feedback.tone });
                          await refreshAll();
                        },
                      },
                    );
                  }}
                >
                  Убрать тариф
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  onClick={(event) => {
                    stopActionClick(event);
                    const nextBlocked = !detail.user.is_blocked;
                    if (!confirmAction(nextBlocked ? "Заблокировать пользователя и остановить доступ?" : "Снять блокировку с пользователя?")) {
                      return;
                    }
                    actionMutation.mutate(
                      { path: `/users/${detail.user.id}/block`, body: { blocked: !detail.user.is_blocked } },
                      {
                        onSuccess: async () => {
                          setNotice(nextBlocked ? "Пользователь заблокирован." : "Пользователь разблокирован.");
                          pushToast({ title: nextBlocked ? "Пользователь заблокирован" : "Пользователь разблокирован", tone: nextBlocked ? "warning" : "success" });
                          await refreshAll();
                        },
                      },
                    );
                  }}
                >
                  {detail.user.is_blocked ? "Снять блок" : "Заблокировать"}
                </Button>
                <Select id="user-protocol" name="preferredProtocol" value={currentProtocol} onChange={(event) => activeUserId && setProtocolOverrides((prev) => ({ ...prev, [activeUserId]: event.target.value }))}>
                  <option value="vless">VLESS</option>
                  <option value="trojan">Trojan + TLS</option>
                </Select>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  onClick={(event) => {
                    stopActionClick(event);
                    if (!confirmAction(`Сохранить предпочитаемый протокол: ${protocolLabel(currentProtocol)}?`)) {
                      return;
                    }
                    actionMutation.mutate(
                      { path: `/users/${detail.user.id}/protocol`, body: { protocol: currentProtocol } },
                      {
                        onSuccess: async () => {
                          setNotice(`Предпочтительный протокол сохранён: ${protocolLabel(currentProtocol)}.`);
                          pushToast({ title: "Протокол обновлён", description: protocolLabel(currentProtocol), tone: "info" });
                          await refreshAll();
                        },
                      },
                    );
                  }}
                  disabled={actionMutation.isPending}
                >
                  Сохранить протокол
                </Button>
              </Card>

              <Card className="space-y-2">
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Новое устройство</div>
                <form className="space-y-2" onSubmit={onDeviceSubmit}>
                  <Input id="device-name" name="deviceName" value={deviceForm.device_name} onChange={(event) => setDeviceForm((prev) => ({ ...prev, device_name: event.target.value }))} placeholder="Название устройства" required />
                  <Select id="device-type" name="deviceType" value={deviceForm.device_type} onChange={(event) => setDeviceForm((prev) => ({ ...prev, device_type: event.target.value }))}>
                    <option value="desktop">Компьютер</option>
                    <option value="mobile">Телефон</option>
                    <option value="router">Роутер</option>
                  </Select>
                  <Select id="device-protocol" name="deviceProtocol" value={deviceForm.protocol} onChange={(event) => setDeviceForm((prev) => ({ ...prev, protocol: event.target.value }))}>
                    <option value="vless">VLESS</option>
                    <option value="trojan">Trojan + TLS</option>
                  </Select>
                  <Select id="device-country" name="deviceCountryCode" value={deviceForm.country_code} onChange={(event) => setDeviceForm((prev) => ({ ...prev, country_code: event.target.value }))}>
                    <option value="de">Германия</option>
                    <option value="dk">Дания</option>
                  </Select>
                  <Button type="submit" className="w-full" disabled={actionMutation.isPending}>Создать устройство</Button>
                </form>
              </Card>

              <Button
                type="button"
                variant="danger"
                className="w-full"
                onClick={(event) => {
                  stopActionClick(event);
                  if (confirmAction("Удалить пользователя вместе с данными доступа?")) {
                    actionMutation.mutate(
                      { path: `/users/${detail.user.id}/delete` },
                      {
                        onSuccess: async () => {
                          setNotice("Пользователь удалён вместе с данными доступа.");
                          pushToast({ title: "Пользователь удалён", description: detail.user.username, tone: "warning" });
                          setSelectedUserId(undefined);
                          const params = new URLSearchParams(searchParams.toString());
                          params.delete("user_id");
                          router.replace(`/users${params.toString() ? `?${params.toString()}` : ""}`, { scroll: false });
                          await refreshAll();
                        },
                      },
                    );
                  }
                }}
              >
                Удалить пользователя
              </Button>
            </div>
          </div>
        </DetailPanel>
      ) : null}
    </div>
  );
}
