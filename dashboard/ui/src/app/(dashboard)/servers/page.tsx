"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Card, DetailPanel, EmptyState, NoticeBanner, SectionHeading, Select, StatusBadge } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useServers, useSession } from "@/hooks/use-dashboard";
import { apiGet, apiPost } from "@/lib/api";
import { ServersPayload } from "@/lib/types";
import { useToasts } from "@/components/toast-center";

function formatPercent(value?: number) {
  return `${Math.round(Number(value || 0))}%`;
}

function formatThroughput(value?: number) {
  const numeric = Number(value || 0);
  if (!numeric) return "0 Мбит/с";
  if (numeric >= 1000) return `${(numeric / 1000).toFixed(2)} Гбит/с`;
  return `${numeric >= 10 ? numeric.toFixed(1) : numeric.toFixed(2)} Мбит/с`;
}

function confirmAction(message: string): boolean {
  if (typeof window === "undefined") return true;
  return window.confirm(message);
}

export default function ServersPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const session = useSession();
  const [selectedServerId, setSelectedServerId] = useState<number | undefined>(
    searchParams.get("server_id") ? Number(searchParams.get("server_id")) : undefined,
  );
  const [migrationTargetId, setMigrationTargetId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const serversQuery = useServers(selectedServerId);
  const permissions = session.data?.admin.permissions ?? {};

  const mutation = useMutation({
    mutationFn: (payload: { path: string; body?: unknown }) => apiPost(payload.path, payload.body),
    onSuccess: async () => {
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["servers"] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
      await queryClient.invalidateQueries({ queryKey: ["traffic"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      pushToast({ title: "Действие не выполнено", description: mutationError.message, tone: "error" });
    },
  });

  if (serversQuery.isLoading) return <PageLoader />;
  if (serversQuery.error || !serversQuery.data) {
    return <PageError message={serversQuery.error?.message || "Не удалось загрузить серверы"} />;
  }

  const { summary, nodes, selected_node, vpn_summary } = serversQuery.data;
  const selectedNode = selected_node ?? null;

  const refreshSnapshot = async () => {
    try {
      const search = new URLSearchParams();
      if (selectedServerId) search.set("server_id", String(selectedServerId));
      search.set("force", "1");
      const payload = await apiGet<ServersPayload>(`/servers${search.toString() ? `?${search.toString()}` : ""}`);
      queryClient.setQueryData(["servers", selectedServerId, false], payload);
      queryClient.setQueryData(["servers", selectedServerId, true], payload);
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
      await queryClient.invalidateQueries({ queryKey: ["traffic"] });
      setNotice("Серверный срез обновлён.");
      pushToast({ title: "Срез обновлён", description: "Получены свежие метрики по нодам.", tone: "success" });
    } catch (refreshError) {
      const message = refreshError instanceof Error ? refreshError.message : "Не удалось обновить серверный срез";
      setError(message);
      pushToast({ title: "Срез не обновлён", description: message, tone: "error" });
    }
  };

  const openServer = (serverId: number) => {
    setSelectedServerId(serverId);
    const params = new URLSearchParams(searchParams.toString());
    params.set("server_id", String(serverId));
    router.replace(`/servers?${params.toString()}`);
  };

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Серверы"
        description="Ноды и действия по ним."
        actions={
          <Button variant="ghost" type="button" onClick={refreshSnapshot}>
            Обновить статус
          </Button>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}

      <div className="grid gap-3 xl:grid-cols-3">
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Нод всего / рабочих</div>
          <div className="mt-2 text-[1.4rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            {summary.total || 0}/{summary.active || 0}
          </div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Деградация / недоступных</div>
          <div className="mt-2 text-[1.4rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            {summary.degradation || 0}/{summary.down || 0}
          </div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Пользователей с доступом</div>
          <div className="mt-2 text-[1.4rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            {vpn_summary.active_access || 0}
          </div>
        </Card>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="grid grid-cols-[0.45fr_1.2fr_0.95fr_0.75fr_0.65fr_0.65fr_0.65fr_0.7fr] gap-3 border-b border-[color:var(--surface-border)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          <span>№</span>
          <span>Название</span>
          <span>IP</span>
          <span>Статус</span>
          <span>CPU</span>
          <span>RAM</span>
          <span>Память</span>
          <span>Устройства</span>
        </div>
        <div className="divide-y divide-[color:var(--surface-border)]">
          {nodes.length ? (
            nodes.map((node, index) => (
              <button
                key={node.id}
                type="button"
                onClick={() => openServer(node.id)}
                className={`grid w-full cursor-pointer grid-cols-[0.45fr_1.2fr_0.95fr_0.75fr_0.65fr_0.65fr_0.65fr_0.7fr] gap-3 px-4 py-3 text-left transition hover:bg-white/35 dark:hover:bg-white/4 ${
                  selectedNode?.id === node.id ? "bg-white/40 dark:bg-white/4" : ""
                }`}
              >
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">{index + 1}</div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-slate-950 dark:text-slate-50">{node.name}</div>
                  <div className="truncate text-[13px] text-[color:var(--text-muted)]">{node.country_name}</div>
                </div>
                <div className="truncate text-[13px] text-slate-700 dark:text-slate-300">{node.public_ip}</div>
                <StatusBadge status={node.status_state || node.overall_state} label={node.status_label || node.status} />
                <div className="text-[13px] text-slate-700 dark:text-slate-300">{formatPercent(node.cpu_percent)}</div>
                <div className="text-[13px] text-slate-700 dark:text-slate-300">{formatPercent(node.memory_used_percent)}</div>
                <div className="text-[13px] text-slate-700 dark:text-slate-300">{formatPercent(node.disk_used_percent)}</div>
                <div className="text-[13px] text-slate-700 dark:text-slate-300">{node.active_devices}/{node.total_devices}</div>
              </button>
            ))
          ) : (
            <div className="px-5 py-10">
              <EmptyState title="Ноды не найдены" description="Пока нет серверов в рабочем реестре." />
            </div>
          )}
        </div>
      </Card>

      {selectedNode ? (
        <DetailPanel
          variant="overlay"
          className="max-w-[980px]"
          bodyClassName="space-y-4"
          title={selectedNode.name}
          subtitle={`${selectedNode.country_name} · ${selectedNode.public_ip}`}
          onClose={() => {
            setSelectedServerId(undefined);
            const params = new URLSearchParams(searchParams.toString());
            params.delete("server_id");
            router.replace(`/servers${params.toString() ? `?${params.toString()}` : ""}`);
          }}
        >
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_290px]">
            <div className="space-y-4">
              <Card className="space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Название</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedNode.name}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Статус</div><div className="mt-1"><StatusBadge status={selectedNode.status_state || selectedNode.overall_state} label={selectedNode.status_label || selectedNode.status} /></div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">IP</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedNode.public_ip}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Host</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedNode.host}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Provider</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedNode.provider}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Ping</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedNode.ping_label}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">CPU</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatPercent(selectedNode.cpu_percent)}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">RAM</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatPercent(selectedNode.memory_used_percent)}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Память</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatPercent(selectedNode.disk_used_percent)}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Устройства</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedNode.active_devices}/{selectedNode.total_devices}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Пользователи</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedNode.active_users}</div></div>
                  <div><div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Трафик</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatThroughput(selectedNode.total_network_mbps)}</div></div>
                </div>
                <div className="rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[13px] text-[color:var(--text-muted)]">
                  {selectedNode.status_message}
                </div>
              </Card>

              <Card className="space-y-2">
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Сервисы</div>
                {selectedNode.service_pills.length ? (
                  selectedNode.service_pills.map((item) => (
                    <div key={`${item.label}-${item.value}`} className="flex items-center justify-between gap-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[13px]">
                      <span className="text-[color:var(--text-muted)]">{item.label}</span>
                      <span className="font-semibold text-slate-950 dark:text-slate-50">{item.value}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-[13px] text-[color:var(--text-muted)]">Нет данных по сервисам.</div>
                )}
              </Card>
            </div>

            <div className="space-y-3">
              <Card className="space-y-2">
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Действия</div>
                <Button
                  type="button"
                  className="justify-start"
                  disabled={!permissions.can_manage_server_actions || mutation.isPending}
                  onClick={() => {
                    if (!confirmAction(`Запустить health check для ${selectedNode.name}?`)) {
                      return;
                    }
                    mutation.mutate(
                      { path: `/servers/${selectedNode.id}/action`, body: { action: "health_check" } },
                      {
                        onSuccess: () => {
                          setNotice(`Проверка ${selectedNode.name} завершена.`);
                          pushToast({ title: "Проверка выполнена", description: selectedNode.name, tone: "info" });
                        },
                      },
                    );
                  }}
                >
                  Health check
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  className="justify-start"
                  disabled={!permissions.can_manage_server_actions || mutation.isPending}
                  onClick={() => {
                    if (!confirmAction(`Перезапустить ноду ${selectedNode.name}?`)) {
                      return;
                    }
                    mutation.mutate(
                      { path: `/servers/${selectedNode.id}/action`, body: { action: "restart" } },
                      {
                        onSuccess: () => {
                          setNotice(`Нода ${selectedNode.name} отправлена на restart.`);
                          pushToast({ title: "Restart отправлен", description: selectedNode.name, tone: "warning" });
                        },
                      },
                    );
                  }}
                >
                  Restart
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="justify-start"
                  disabled={!permissions.can_manage_server_actions || mutation.isPending}
                  onClick={() => {
                    if (!confirmAction(`Переключить maintenance-режим для ${selectedNode.name}?`)) {
                      return;
                    }
                    mutation.mutate(
                      { path: `/servers/${selectedNode.id}/action`, body: { action: "maintenance" } },
                      {
                        onSuccess: () => {
                          setNotice(`Статус ${selectedNode.name} обновлён.`);
                          pushToast({ title: "Maintenance обновлён", description: selectedNode.name, tone: "info" });
                        },
                      },
                    );
                  }}
                >
                  Maintenance
                </Button>
                <Select
                  id="server-migration-target"
                  name="serverMigrationTarget"
                  value={migrationTargetId}
                  onChange={(event) => setMigrationTargetId(event.target.value)}
                >
                  <option value="">Куда мигрировать</option>
                  {(selectedNode.migration_targets ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · {item.country_name}
                    </option>
                  ))}
                </Select>
                <Button
                  type="button"
                  variant="ghost"
                  className="justify-start"
                  disabled={!permissions.can_manage_server_actions || !migrationTargetId || mutation.isPending}
                  onClick={() => {
                    const target = (selectedNode.migration_targets ?? []).find((item) => String(item.id) === migrationTargetId);
                    const targetLabel = target ? `${target.name} (${target.country_name})` : "выбранную ноду";
                    if (!confirmAction(`Запустить миграцию ${selectedNode.name} на ${targetLabel}?`)) {
                      return;
                    }
                    mutation.mutate(
                      {
                        path: `/servers/${selectedNode.id}/action`,
                        body: { action: "migrate", target_server_id: Number(migrationTargetId) },
                      },
                      {
                        onSuccess: () => {
                          setNotice(`Для ${selectedNode.name} запущена миграция.`);
                          pushToast({ title: "Миграция запущена", description: selectedNode.name, tone: "warning" });
                        },
                      },
                    );
                  }}
                >
                  Миграция
                </Button>
              </Card>
            </div>
          </div>
        </DetailPanel>
      ) : null}
    </div>
  );
}
