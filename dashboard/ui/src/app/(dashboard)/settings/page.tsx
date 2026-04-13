"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { Button, Card, Input, NoticeBanner, SectionHeading, StatusBadge } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useSession, useSettings } from "@/hooks/use-dashboard";
import { apiPost } from "@/lib/api";

const tabs = [
  { key: "payments", label: "Платежи" },
  { key: "keys", label: "Ключи API" },
  { key: "servers", label: "Серверы" },
  { key: "bots", label: "Боты" },
  { key: "plans", label: "Тарифы" },
  { key: "roles", label: "Роли и права" },
  { key: "notifications", label: "Уведомления" },
  { key: "integrations", label: "Интеграции" },
  { key: "services", label: "Сервисы и env" },
] as const;

const paymentLabels: Record<string, { title: string; description: string }> = {
  telegram_stars: {
    title: "Telegram Stars",
    description: "Нативная оплата внутри Telegram для цифровой услуги.",
  },
  sbp_platega: {
    title: "СБП (Platega)",
    description: "Основной auto-flow: внешний провайдер, callback через landing и panel sync.",
  },
  crypto_platega: {
    title: "Криптовалюта (Platega)",
    description: "Основной auto-flow: внешний крипто-чекаут и автоподтверждение без ручного review.",
  },
  sbp_manual: {
    title: "Ручная СБП",
    description: "Скрытый emergency fallback. В пользовательском контуре должен оставаться выключенным.",
  },
  crypto_manual: {
    title: "Ручная крипта",
    description: "Скрытый emergency fallback. В пользовательском контуре должен оставаться выключенным.",
  },
  crypto_bot: {
    title: "Crypto Bot API",
    description: "Системная интеграция, оставленная в коде. В пользовательском контуре сейчас скрыта.",
  },
};

function confirmAction(message: string): boolean {
  if (typeof window === "undefined") return true;
  return window.confirm(message);
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const session = useSession();
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["key"]>("payments");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [envForm, setEnvForm] = useState({ key: "", value: "", applyRuntime: true });
  const [clearedLogs, setClearedLogs] = useState<Record<string, boolean>>({});
  const [tariffsForm, setTariffsForm] = useState<Record<string, string>>({});
  const [adminRoleForm, setAdminRoleForm] = useState<Record<number, { role: string; is_active: boolean }>>({});

  const settingsQuery = useSettings();

  const mutation = useMutation({
    mutationFn: (payload: { path: string; body?: unknown }) => apiPost(payload.path, payload.body),
    onSuccess: async () => {
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
      await queryClient.invalidateQueries({ queryKey: ["servers"] });
      await queryClient.invalidateQueries({ queryKey: ["payments"] });
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
    },
  });

  const handleTariffChange = (key: string, value: string) => {
    setTariffsForm((prev) => ({ ...prev, [key]: value }));
  };

  const apiKeyRows = useMemo(() => settingsQuery.data?.api_keys ?? [], [settingsQuery.data?.api_keys]);
  const currentAdminRole = session.data?.admin.role ?? "";
  const currentTelegramId = Number(session.data?.admin.telegram_id || 0);

  if (settingsQuery.isLoading) return <PageLoader />;
  if (settingsQuery.error || !settingsQuery.data) {
    return <PageError message={settingsQuery.error?.message || "Не удалось загрузить настройки"} />;
  }

  const {
    service_statuses,
    logs,
    env_rows,
    tariffs,
    tariff_options,
    managed_servers,
    payment_methods,
    available_roles,
    admins,
    role_matrix,
    notification_profiles,
    integrations,
  } = settingsQuery.data;
  const safeTariffOptions = Array.isArray(tariff_options)
    ? tariff_options.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    : [];
  const safeTariffs = {
    tariff_1m_rub: Number(tariffs?.tariff_1m_rub ?? 0),
    tariff_3m_rub: Number(tariffs?.tariff_3m_rub ?? 0),
    tariff_6m_rub: Number(tariffs?.tariff_6m_rub ?? 0),
    tariff_12m_rub: Number(tariffs?.tariff_12m_rub ?? 0),
  };
  const notificationCategories = Array.isArray(notification_profiles) && notification_profiles.length
    ? (notification_profiles[0]?.categories ?? [])
    : [];
  const notificationGridTemplate = `minmax(220px,1.2fr) repeat(${Math.max(notificationCategories.length, 1)}, minmax(96px,0.65fr))`;

  const visibleLogEntries = Object.entries(logs).map(([key, value]) => [key, clearedLogs[key] ? "" : value] as const);

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow=""
        title="Настройки"
        description="Роли, уведомления, сервисы и платёжный стек."
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}

      <Card className="p-3">
        <div className="flex flex-wrap gap-3">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-2xl px-4 py-2.5 text-sm font-medium transition ${
                activeTab === tab.key
                  ? "bg-slate-950 text-white shadow-lg shadow-slate-300/40 dark:bg-blue-600 dark:shadow-blue-950/40"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </Card>

      {activeTab === "payments" ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_420px]">
          <Card>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Payment stack</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
              Активные и скрытые способы оплаты
            </h3>
              <div className="mt-5 grid gap-3">
              {Object.entries(payment_methods).map(([key, enabled]) => {
                  const meta = paymentLabels[key] ?? { title: key, description: "Без дополнительного описания." };
                  return (
                    <div key={key} className="grid gap-3 rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70 md:grid-cols-[minmax(0,1fr)_120px]">
                      <div className="min-w-0">
                        <div className="font-semibold text-slate-950 dark:text-slate-50">{meta.title}</div>
                        <div className="mt-1 break-words text-sm leading-6 text-slate-500 dark:text-slate-400">{meta.description}</div>
                      </div>
                      <div className="flex items-center justify-start md:justify-end">
                        <StatusBadge status={enabled ? "confirmed" : "cancelled"} label={enabled ? "Активен" : "Скрыт"} />
                      </div>
                    </div>
                  );
                })}
            </div>
          </Card>

          <Card>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Infrastructure</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
              Managed servers
            </h3>
            <div className="mt-5 space-y-3">
              {managed_servers.map((server) => (
                <div key={String(server.id)} className="rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-slate-950 dark:text-slate-50">{String(server.name)}</div>
                      <div className="mt-1 break-words text-sm text-slate-500 dark:text-slate-400">
                        {String(server.country_name)} · {String(server.provider)}
                      </div>
                      <div className="text-sm text-slate-500 dark:text-slate-400">{String(server.public_ip)}</div>
                    </div>
                    <StatusBadge status={String(server.status)} label={String(server.status)} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      ) : null}

      {activeTab === "keys" ? (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Secrets overview</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            Маскированные ключи и токены
          </h3>
          <div className="mt-5 grid gap-3 lg:grid-cols-2">
            {apiKeyRows.map(([key, value]) => (
              <div key={key} className="rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
                <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{key}</div>
                <div className="mt-2 break-all font-mono text-sm text-slate-700 dark:text-slate-300">{value}</div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {activeTab === "servers" ? (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Server configuration</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            Реестр нод и рабочий статус
          </h3>
          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {managed_servers.map((server) => (
              <div key={String(server.id)} className="rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-semibold text-slate-950 dark:text-slate-50">{String(server.name)}</div>
                    <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{String(server.country_name)}</div>
                  </div>
                  <StatusBadge status={String(server.status)} label={String(server.status)} />
                </div>
                <div className="mt-4 space-y-1 text-sm text-slate-500 dark:text-slate-400">
                  <div>Provider: {String(server.provider)}</div>
                  <div className="break-words">IP: {String(server.public_ip)}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {activeTab === "bots" ? (
        <div className="grid gap-4">
          <Card>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Service status</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
              Живой статус сервисов
            </h3>
            <div className="mt-5 grid gap-3">
              {Object.entries(service_statuses).map(([key, item]) => (
                <div key={key} className="flex items-center justify-between gap-3 rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-950 dark:text-slate-50">{item.label}</div>
                    <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{key}</div>
                  </div>
                  <StatusBadge status={item.status} label={item.status} />
                </div>
              ))}
            </div>
          </Card>
        </div>
      ) : null}

      {activeTab === "plans" ? (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Tariff editor</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            Тарифы для бота и сайта
          </h3>
          <div className="mt-5 space-y-3">
            {safeTariffOptions.map((item) => (
              <div
                key={String(item.code)}
                className="grid gap-4 rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70 md:grid-cols-[minmax(0,1fr)_minmax(220px,260px)]"
              >
                <div>
                  <div className="font-semibold text-slate-950 dark:text-slate-50">{String(item.title)}</div>
                  <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    {String(item.duration_days)} дней · код {String(item.code)}
                  </div>
                </div>
                <div className="flex min-w-0 items-center gap-2 md:justify-end">
                  <Input
                    id={`tariff-${String(item.code)}-rub`}
                    name={`tariff${String(item.code).toUpperCase()}Rub`}
                    type="number"
                    min="0"
                    className="w-full md:max-w-[220px]"
                    value={tariffsForm[String(item.code)] ?? String(item.rub_price ?? "")}
                    onChange={(event) => handleTariffChange(String(item.code), event.target.value)}
                  />
                  <span className="shrink-0 text-sm text-slate-500 dark:text-slate-400">₽</span>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button
              onClick={() => {
                if (!confirmAction("Обновить тарифы для бота и лендинга?")) {
                  return;
                }
                mutation.mutate(
                  {
                    path: "/settings/tariffs",
                    body: {
                      tariff_1m_rub: Number(tariffsForm["1m"] || safeTariffs.tariff_1m_rub),
                      tariff_3m_rub: Number(tariffsForm["3m"] || safeTariffs.tariff_3m_rub),
                      tariff_6m_rub: Number(tariffsForm["6m"] || safeTariffs.tariff_6m_rub),
                      tariff_12m_rub: Number(tariffsForm["12m"] || safeTariffs.tariff_12m_rub),
                    },
                  },
                  { onSuccess: () => setNotice("Тарифы обновлены и синхронизированы для бота и лендинга.") },
                );
              }}
            >
              Обновить тарифы
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setTariffsForm({
                  "1m": String(safeTariffs.tariff_1m_rub),
                  "3m": String(safeTariffs.tariff_3m_rub),
                  "6m": String(safeTariffs.tariff_6m_rub),
                  "12m": String(safeTariffs.tariff_12m_rub),
                });
              }}
            >
              Сбросить в текущие значения
            </Button>
          </div>
        </Card>
      ) : null}

      {activeTab === "services" ? (
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Services & env</p>
                <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
                  Логи сервисов и .env
                </h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500 dark:text-slate-400">
                  Журналы читаются в полном размере, а очистка касается только текущего предпросмотра, чтобы было легче сосредоточиться на нужном сервисе.
                </p>
              </div>
            </div>
          </Card>

          <div className="space-y-4">
            {visibleLogEntries.map(([key, value]) => {
              const serviceName =
                key === "main_bot"
                  ? "amonora-bot.service"
                  : key === "support_bot"
                    ? "amonora-support-bot.service"
                    : "amonora-dashboard.service";

              return (
                <Card key={key}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">{key}</p>
                      <h3 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Journal tail</h3>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="ghost"
                        onClick={() => {
                          if (!confirmAction(`Перезапустить сервис ${serviceName}?`)) {
                            return;
                          }
                          mutation.mutate(
                            { path: "/settings/services/action", body: { service_name: serviceName, action: "restart" } },
                            { onSuccess: () => setNotice(`Сервис ${serviceName} отправлен на restart.`) },
                          );
                        }}
                      >
                        Restart
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={async () => {
                          await Promise.all([
                            queryClient.invalidateQueries({ queryKey: ["settings"] }),
                            queryClient.invalidateQueries({ queryKey: ["servers"] }),
                            queryClient.invalidateQueries({ queryKey: ["overview"] }),
                          ]);
                          setNotice(`Статус ${serviceName} обновлён.`);
                        }}
                      >
                        <RefreshCw className="mr-2 h-4 w-4" />
                        Обновить
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => setClearedLogs((prev) => ({ ...prev, [key]: !prev[key] }))}
                      >
                        {clearedLogs[key] ? "Вернуть" : "Очистить"}
                      </Button>
                    </div>
                  </div>
                  <pre className="mt-4 max-h-[360px] overflow-auto rounded-[28px] bg-slate-950 p-5 text-xs leading-6 text-slate-200">
                    {value || "Просмотр очищен. Нажми «Вернуть», чтобы снова увидеть journal tail."}
                  </pre>
                </Card>
              );
            })}
          </div>

          <div className="grid gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
            <Card>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Environment update</p>
              <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
                Обновить переменную .env
              </h3>
              <div className="mt-5 space-y-3">
                <Input id="settings-env-key" name="envKey" placeholder="KEY" value={envForm.key} onChange={(event) => setEnvForm((prev) => ({ ...prev, key: event.target.value }))} />
                <Input id="settings-env-value" name="envValue" placeholder="VALUE" value={envForm.value} onChange={(event) => setEnvForm((prev) => ({ ...prev, value: event.target.value }))} />
                <div className="rounded-[22px] border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-300">
                  Сохранение идёт через staged apply: `.env` будет обновлён, сервисы перезапустятся и пройдут проверку.
                  Если проверка не сойдётся, изменение автоматически откатится.
                </div>
                <Button
                  className="w-full"
                  onClick={() => {
                    const confirmMessage = `Сохранить переменную ${envForm.key || "KEY"} в .env и сразу применить её через restart+verify?`;
                    if (!confirmAction(confirmMessage)) {
                      return;
                    }
                    mutation.mutate(
                      { path: "/settings/env", body: { key: envForm.key, value: envForm.value, apply_runtime: true } },
                      {
                        onSuccess: (payload: unknown) => {
                          const envUpdateResult = (
                            payload as {
                              env_update_result?: {
                                affected_services?: string[];
                                restart_required?: boolean;
                                runtime_apply?: {
                                  applied_ok?: boolean;
                                  verified_services?: string[];
                                  failed_services?: { service_name: string; error: string }[];
                                } | null;
                              };
                            }
                          )?.env_update_result;
                          const affectedServices = Array.isArray(envUpdateResult?.affected_services)
                            ? (envUpdateResult?.affected_services ?? [])
                            : [];
                          const restartRequired = Boolean(envUpdateResult?.restart_required);
                          const runtimeApply = envUpdateResult?.runtime_apply;
                          const failedServices = Array.isArray(runtimeApply?.failed_services) ? runtimeApply?.failed_services ?? [] : [];
                          const verifiedServices = Array.isArray(runtimeApply?.verified_services) ? runtimeApply?.verified_services ?? [] : [];
                          const suffix = runtimeApply
                            ? failedServices.length
                              ? ` Применение частично не прошло: ${failedServices.map((item) => `${item.service_name} (${item.error})`).join(", ")}.`
                              : verifiedServices.length
                                ? ` Изменение применено и проверено: ${verifiedServices.join(", ")}.`
                                : restartRequired
                                  ? " Нужен restart сервисов."
                                  : ""
                            : restartRequired
                              ? affectedServices.length
                                ? ` Требуется restart: ${affectedServices.join(", ")}.`
                                : " Требуется restart сервисов."
                              : "";
                          setNotice(`Переменная ${envForm.key} сохранена.${suffix}`);
                          setEnvForm({ key: "", value: "", applyRuntime: true });
                        },
                      },
                    );
                  }}
                >
                  Сохранить переменную
                </Button>
              </div>
            </Card>

            <Card>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Current env snapshot</p>
              <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
                Маскированные переменные окружения
              </h3>
              <div className="mt-5 grid max-h-[520px] gap-3 overflow-auto pr-1 md:grid-cols-2">
                {env_rows.map(([key, value]) => (
                  <div key={key} className="rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
                    <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{key}</div>
                    <div className="mt-2 break-all font-mono text-sm text-slate-700 dark:text-slate-300">{value}</div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      ) : null}

      {activeTab === "roles" ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
          <Card>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
              Роли и разрешения control-center
            </h3>
            <div className="mt-5 overflow-auto">
              <div className="min-w-[720px] space-y-2">
                <div className="grid grid-cols-[1.2fr_0.5fr_0.6fr_0.6fr] gap-3 px-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  <span>Разрешение</span>
                  <span>Владелец</span>
                  <span>Техадмин</span>
                  <span>Менеджер</span>
                </div>
                {(role_matrix ?? []).map((row) => (
                  <div key={row.permission} className="grid grid-cols-[1.2fr_0.5fr_0.6fr_0.6fr] gap-3 rounded-[22px] border border-slate-200 bg-slate-50/90 px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-900/70">
                    <div className="font-medium text-slate-950 dark:text-slate-50">{row.label || row.permission}</div>
                    <StatusBadge status={row.owner ? "confirmed" : "cancelled"} label={row.owner ? "Да" : "Нет"} />
                    <Button
                      type="button"
                      variant={row.tech_admin ? "primary" : "ghost"}
                      disabled={currentAdminRole !== "owner" || !row.tech_admin_editable || mutation.isPending}
                      onClick={() => {
                        const nextEnabled = !row.tech_admin;
                        if (!confirmAction(`${nextEnabled ? "Включить" : "Выключить"} разрешение «${row.label || row.permission}» для техадмина?`)) {
                          return;
                        }
                        mutation.mutate(
                          {
                            path: "/settings/permissions",
                            body: { role: "tech_admin", permission: row.permission, enabled: nextEnabled },
                          },
                          {
                            onSuccess: () => setNotice(`Разрешение «${row.label || row.permission}» для техадмина обновлено.`),
                          },
                        );
                      }}
                    >
                      {row.tech_admin ? "Да" : "Нет"}
                    </Button>
                    <Button
                      type="button"
                      variant={row.manager ? "primary" : "ghost"}
                      disabled={currentAdminRole !== "owner" || !row.manager_editable || mutation.isPending}
                      onClick={() => {
                        const nextEnabled = !row.manager;
                        if (!confirmAction(`${nextEnabled ? "Включить" : "Выключить"} разрешение «${row.label || row.permission}» для менеджера?`)) {
                          return;
                        }
                        mutation.mutate(
                          {
                            path: "/settings/permissions",
                            body: { role: "support_admin", permission: row.permission, enabled: nextEnabled },
                          },
                          {
                            onSuccess: () => setNotice(`Разрешение «${row.label || row.permission}» для менеджера обновлено.`),
                          },
                        );
                      }}
                    >
                      {row.manager ? "Да" : "Нет"}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <Card>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
              Активные администраторы
            </h3>
            <div className="mt-5 space-y-3">
              {(admins ?? []).map((admin) => (
                <div key={admin.id} className="rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-slate-950 dark:text-slate-50">{admin.display_name}</div>
                      <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">@{admin.username}</div>
                      <div className="text-sm text-slate-500 dark:text-slate-400">Telegram ID: {admin.telegram_id ?? "—"}</div>
                    </div>
                    <StatusBadge status={admin.is_active ? "confirmed" : "cancelled"} label={admin.role_name} />
                  </div>
                  {currentAdminRole === "owner" ? (
                    <div className="mt-4 grid gap-2 sm:grid-cols-[minmax(0,1fr)_150px_auto]">
                      <select
                        id={`admin-role-${admin.id}`}
                        name={`adminRole${admin.id}`}
                        value={adminRoleForm[admin.id]?.role ?? admin.role}
                        onChange={(event) =>
                          setAdminRoleForm((prev) => ({
                            ...prev,
                            [admin.id]: {
                              role: event.target.value,
                              is_active: prev[admin.id]?.is_active ?? admin.is_active,
                            },
                          }))
                        }
                        className="h-9 rounded-[14px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 text-[13px] text-slate-900 outline-none dark:bg-[var(--surface-muted)] dark:text-slate-100"
                      >
                        {(available_roles ?? []).map((role) => (
                          <option key={role.value} value={role.value}>
                            {role.label}
                          </option>
                        ))}
                      </select>
                      <select
                        id={`admin-active-${admin.id}`}
                        name={`adminActive${admin.id}`}
                        value={(adminRoleForm[admin.id]?.is_active ?? admin.is_active) ? "active" : "inactive"}
                        onChange={(event) =>
                          setAdminRoleForm((prev) => ({
                            ...prev,
                            [admin.id]: {
                              role: prev[admin.id]?.role ?? admin.role,
                              is_active: event.target.value === "active",
                            },
                          }))
                        }
                        className="h-9 rounded-[14px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 text-[13px] text-slate-900 outline-none dark:bg-[var(--surface-muted)] dark:text-slate-100"
                      >
                        <option value="active">Активен</option>
                        <option value="inactive">Отключён</option>
                      </select>
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => {
                          const nextRole = adminRoleForm[admin.id]?.role ?? admin.role;
                          const nextIsActive = adminRoleForm[admin.id]?.is_active ?? admin.is_active;
                          const stateLabel = nextIsActive ? "активен" : "отключён";
                          if (!confirmAction(`Обновить администратора ${admin.display_name}: роль ${nextRole}, статус ${stateLabel}?`)) {
                            return;
                          }
                          mutation.mutate(
                            {
                              path: `/settings/admins/${admin.id}`,
                              body: {
                                role: nextRole,
                                is_active: nextIsActive,
                              },
                            },
                            {
                              onSuccess: () => setNotice(`Права администратора ${admin.display_name} обновлены.`),
                            },
                          );
                        }}
                      >
                        Сохранить
                      </Button>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        </div>
      ) : null}

      {activeTab === "notifications" ? (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Уведомления</p>
          <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">Настройки уведомлений по администраторам</h3>
          <div className="mt-5 overflow-auto">
            {(notification_profiles ?? []).length ? (
              <div className="min-w-[900px] space-y-2">
                <div className="grid gap-3 px-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400" style={{ gridTemplateColumns: notificationGridTemplate }}>
                  <span>Администратор</span>
                  {notificationCategories.map((category) => (
                    <span key={`notification-head-${category.key}`}>{category.label}</span>
                  ))}
                </div>
                {(notification_profiles ?? []).map((profile) => (
                  <div key={profile.telegram_id} className="grid gap-3 rounded-[22px] border border-slate-200 bg-slate-50/90 px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-900/70" style={{ gridTemplateColumns: notificationGridTemplate }}>
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-950 dark:text-slate-50">{profile.display_name}</div>
                      <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                        {profile.username ? `@${profile.username}` : "без username"} · {profile.role}
                      </div>
                    </div>
                    {(profile.categories ?? []).map((category) => {
                      const canEdit = currentAdminRole === "owner" || currentTelegramId === Number(profile.telegram_id);
                      return (
                        <Button
                          key={`${profile.telegram_id}-${category.key}`}
                          type="button"
                          variant={category.enabled ? "primary" : "ghost"}
                          disabled={!canEdit || category.mandatory || mutation.isPending}
                          onClick={() => {
                            const nextStateLabel = category.enabled ? "выключить" : "включить";
                            if (!confirmAction(`${nextStateLabel === "выключить" ? "Выключить" : "Включить"} уведомления «${category.label}» для ${profile.display_name}?`)) {
                              return;
                            }
                            mutation.mutate(
                              {
                                path: "/settings/notifications",
                                body: {
                                  telegram_id: Number(profile.telegram_id),
                                  category: category.key,
                                  enabled: !category.enabled,
                                },
                              },
                              {
                                onSuccess: () => setNotice(`Уведомления «${category.label}» обновлены для ${profile.display_name}.`),
                              },
                            );
                          }}
                          title={category.label}
                        >
                          {category.mandatory ? "Всегда" : category.enabled ? "Вкл" : "Выкл"}
                        </Button>
                      );
                    })}
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-[24px] border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                Профили уведомлений пока не настроены или ещё не прочитаны из control bot storage.
              </div>
            )}
          </div>
        </Card>
      ) : null}

      {activeTab === "integrations" ? (
        <div className="grid gap-4">
          <Card>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-600">Integrations map</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
              Связи панели с ботами и сервисами
            </h3>
            <div className="mt-5 space-y-3">
              {(integrations ?? []).map((integration) => (
                <div key={integration.key} className="rounded-[24px] border border-slate-200 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/70">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-semibold text-slate-950 dark:text-slate-50">{integration.label}</div>
                      <div className="mt-1 break-words text-sm leading-6 text-slate-500 dark:text-slate-400">{integration.description}</div>
                    </div>
                    <StatusBadge status={integration.status} label={integration.status} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
