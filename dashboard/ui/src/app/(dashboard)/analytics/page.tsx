"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Copy, Plus, RefreshCw } from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { DetailPanel, Button, Card, EmptyState, Input, MetricCard, NoticeBanner, SectionHeading, StatusBadge } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useCampaignAnalytics, useCampaignAnalyticsDetail, useSession } from "@/hooks/use-dashboard";
import { apiPost } from "@/lib/api";
import { useToasts } from "@/components/toast-center";
import { CampaignAnalyticsDetailPayload } from "@/lib/types";

const PERIOD_PRESETS: Array<{ key: string; label: string }> = [
  { key: "7d", label: "7 дней" },
  { key: "30d", label: "30 дней" },
  { key: "this_month", label: "Этот месяц" },
  { key: "last_month", label: "Прошлый месяц" },
];

function isValidIsoDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

export default function AnalyticsCampaignsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const session = useSession();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [campaignName, setCampaignName] = useState("");
  const [ctaLabel, setCtaLabel] = useState("Попробовать бесплатно");
  const [notice, setNotice] = useState("");
  const [periodKey, setPeriodKey] = useState(searchParams.get("period_key") || "30d");
  const [dateFrom, setDateFrom] = useState(searchParams.get("date_from") || "");
  const [dateTo, setDateTo] = useState(searchParams.get("date_to") || "");
  const deferredSearch = useDeferredValue(search);
  const deferredPeriodKey = useDeferredValue(periodKey);
  const deferredDateFrom = useDeferredValue(dateFrom);
  const deferredDateTo = useDeferredValue(dateTo);
  const selectedCampaignId = Number(searchParams.get("campaign_id") || 0) || undefined;
  const permissions = session.data?.admin.permissions ?? {};
  const canManageCampaigns = Boolean(permissions.can_manage_payments);

  const campaignsQuery = useCampaignAnalytics(deferredSearch, {
    periodKey: deferredPeriodKey,
    dateFrom: deferredDateFrom,
    dateTo: deferredDateTo,
  });
  const detailQuery = useCampaignAnalyticsDetail(selectedCampaignId, {
    periodKey: deferredPeriodKey,
    dateFrom: deferredDateFrom,
    dateTo: deferredDateTo,
  });

  useEffect(() => {
    setSearch(searchParams.get("q") || "");
    setPeriodKey(searchParams.get("period_key") || "30d");
    setDateFrom(searchParams.get("date_from") || "");
    setDateTo(searchParams.get("date_to") || "");
  }, [searchParams]);

  const replaceRouteParams = (mutate: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(searchParams.toString());
    mutate(params);
    router.replace(`/analytics${params.toString() ? `?${params.toString()}` : ""}`);
  };

  const applyPeriodPreset = (nextPeriod: string) => {
    setPeriodKey(nextPeriod);
    if (nextPeriod !== "custom") {
      setDateFrom("");
      setDateTo("");
    }
    replaceRouteParams((params) => {
      params.set("period_key", nextPeriod);
      if (nextPeriod !== "custom") {
        params.delete("date_from");
        params.delete("date_to");
      }
    });
  };

  const applyCustomPeriod = () => {
    const safeFrom = dateFrom.trim();
    const safeTo = dateTo.trim();
    if (!isValidIsoDate(safeFrom) || !isValidIsoDate(safeTo) || safeFrom > safeTo) {
      pushToast({
        title: "Неверный диапазон",
        description: "Укажи даты в формате ГГГГ-ММ-ДД и проверь, что дата «с» не позже даты «по».",
        tone: "warning",
      });
      return;
    }
    setPeriodKey("custom");
    replaceRouteParams((params) => {
      params.set("period_key", "custom");
      params.set("date_from", safeFrom);
      params.set("date_to", safeTo);
    });
  };

  const createMutation = useMutation({
    mutationFn: (payload: { topic_brief: string; cta_label: string }) => apiPost<CampaignAnalyticsDetailPayload>("/analytics/campaigns", payload),
    onSuccess: async (payload) => {
      setNotice("Кампания создана.");
      setCampaignName("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["analytics-campaigns"] }),
        queryClient.invalidateQueries({ queryKey: ["analytics-campaign-detail"] }),
      ]);
      if (payload?.id) {
        replaceRouteParams((params) => params.set("campaign_id", String(payload.id)));
      }
    },
    onError: (error: Error) => {
      pushToast({ title: "Не удалось создать кампанию", description: error.message, tone: "error" });
    },
  });

  const copyToClipboard = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      pushToast({ title: "Ссылка скопирована", description: value, tone: "success" });
    } catch (error) {
      pushToast({
        title: "Не удалось скопировать ссылку",
        description: error instanceof Error ? error.message : "Буфер обмена недоступен",
        tone: "error",
      });
    }
  };

  const refreshQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["analytics-campaigns"] }),
      queryClient.invalidateQueries({ queryKey: ["analytics-campaign-detail"] }),
    ]);
  };

  const summaryCards = useMemo(() => {
    const summary = campaignsQuery.data?.summary;
    return [
      {
        label: "Всего переходов",
        value: String(summary?.total_transitions ?? 0),
        helper: "все касания tracking-ссылок",
      },
      {
        label: "Оплатили",
        value: String(summary?.total_paid ?? 0),
        helper: "успешные первичные оплаты",
      },
      {
        label: "Конверсия",
        value: `${Number(summary?.overall_conversion_rate ?? 0).toFixed(2)}%`,
        helper: `${summary?.total_bot_starts ?? 0} start и ${summary?.total_trial_started ?? 0} trial`,
      },
      {
        label: "Кампаний",
        value: String(summary?.total_campaigns ?? 0),
        helper: `${summary?.total_key_issued ?? 0} выдач ключей и ${summary?.total_renewed ?? 0} продлений`,
      },
    ];
  }, [campaignsQuery.data?.summary]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void refreshQueries();
    }, 30_000);
    return () => window.clearInterval(intervalId);
  }, [searchParams]);

  if (campaignsQuery.isLoading) return <PageLoader />;
  if (campaignsQuery.error || !campaignsQuery.data) {
    return <PageError message={campaignsQuery.error?.message || "Не удалось загрузить аналитику кампаний"} />;
  }

  const rows = campaignsQuery.data.campaigns;

  return (
    <div className="space-y-4">
      <SectionHeading
        eyebrow="Маркетинг"
        title="Аналитика кампаний"
        description="Отслеживайте эффективность кампаний: переходы, start, триалы, выдачу ключей, оплаты и продления. Данные обновляются автоматически каждые 30 секунд."
        actions={
          <>
            <Input
              id="campaign-analytics-search"
              name="campaignAnalyticsSearch"
              value={search}
              onChange={(event) => {
                const value = event.target.value;
                setSearch(value);
                replaceRouteParams((params) => {
                  if (value.trim()) params.set("q", value.trim());
                  else params.delete("q");
                });
              }}
              placeholder="Название, token, CTA"
              className="w-full md:w-64"
            />
            <Button variant="ghost" onClick={() => void refreshQueries()} disabled={campaignsQuery.isFetching}>
              <RefreshCw className={`mr-2 h-3.5 w-3.5 ${campaignsQuery.isFetching ? "animate-spin" : ""}`} />
              Обновить
            </Button>
          </>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {PERIOD_PRESETS.map((preset) => (
            <Button
              key={preset.key}
              variant={periodKey === preset.key ? "primary" : "ghost"}
              onClick={() => applyPeriodPreset(preset.key)}
            >
              {preset.label}
            </Button>
          ))}
          <Button variant={periodKey === "custom" ? "primary" : "ghost"} onClick={() => setPeriodKey("custom")}>
            Свой период
          </Button>
        </div>
        <div className="grid gap-2 md:grid-cols-[170px_170px_auto]">
          <Input
            id="analytics-date-from"
            name="analyticsDateFrom"
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
            disabled={periodKey !== "custom"}
          />
          <Input
            id="analytics-date-to"
            name="analyticsDateTo"
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
            disabled={periodKey !== "custom"}
          />
          <Button
            variant="secondary"
            onClick={applyCustomPeriod}
            disabled={periodKey !== "custom" || !dateFrom || !dateTo || campaignsQuery.isFetching}
            className="w-full md:w-auto"
          >
            Применить даты
          </Button>
        </div>
        <div className="text-[12px] text-[color:var(--text-muted)]">
          Текущий срез: {campaignsQuery.data.period?.label || "Последние 30 дней"} · {campaignsQuery.data.period?.start || "—"} →{" "}
          {campaignsQuery.data.period?.end || "—"}
        </div>
      </Card>

      <div className="grid gap-3 xl:grid-cols-4">
        {summaryCards.map((item) => (
          <MetricCard key={item.label} label={item.label} value={item.value} helper={item.helper} />
        ))}
      </div>

      {canManageCampaigns ? (
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-[14px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Новая кампания</h3>
              <p className="text-[12px] leading-5 text-[color:var(--text-muted)]">
                Создаём отдельный `start`-token для оффера и сразу получаем ссылку для Telegram.
              </p>
            </div>
            <div className="flex items-center gap-2 text-[13px] text-[color:var(--text-muted)]">
              <BarChart3 className="h-4 w-4" />
              <span>{rows.length} в списке</span>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_240px_auto]">
            <label className="space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Название кампании</div>
              <Input
                id="campaign-name"
                name="campaignName"
                value={campaignName}
                onChange={(event) => setCampaignName(event.target.value)}
                placeholder="Например: Instagram Reels / май 2026"
              />
            </label>
            <label className="space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">CTA</div>
              <Input
                id="campaign-cta"
                name="campaignCta"
                value={ctaLabel}
                onChange={(event) => setCtaLabel(event.target.value)}
                placeholder="Попробовать бесплатно"
              />
            </label>
            <div className="flex items-end">
              <Button
                className="w-full md:w-auto"
                onClick={() => createMutation.mutate({ topic_brief: campaignName.trim(), cta_label: ctaLabel.trim() || "Попробовать бесплатно" })}
                disabled={createMutation.isPending || !campaignName.trim()}
              >
                <Plus className="mr-2 h-3.5 w-3.5" />
                {createMutation.isPending ? "Создание..." : "Создать"}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      <Card className="overflow-hidden p-0">
        {rows.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-[13px]">
              <thead className="border-b border-[color:var(--surface-border)] bg-[var(--surface-strong)] text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
                <tr>
                  <th className="px-3 py-3 font-semibold">Кампания</th>
                  <th className="px-3 py-3 font-semibold">Создана</th>
                  <th className="px-3 py-3 font-semibold">Переходы</th>
                  <th className="px-3 py-3 font-semibold">Start</th>
                  <th className="px-3 py-3 font-semibold">Триал</th>
                  <th className="px-3 py-3 font-semibold">Ключ</th>
                  <th className="px-3 py-3 font-semibold">Оплаты</th>
                  <th className="px-3 py-3 font-semibold">Продления</th>
                  <th className="px-3 py-3 font-semibold">Конверсия</th>
                  <th className="px-3 py-3 font-semibold text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((campaign) => (
                  <tr key={campaign.id} className="border-b border-[color:var(--surface-border)] last:border-b-0">
                    <td className="px-3 py-3 align-top">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-950 dark:text-slate-50">{campaign.name}</span>
                          <StatusBadge status={campaign.status} label={campaign.status_label} />
                        </div>
                        <div className="truncate text-[12px] text-[color:var(--text-muted)]">{campaign.token}</div>
                      </div>
                    </td>
                    <td className="px-3 py-3 align-top text-[color:var(--text-muted)]">
                      {new Date(campaign.created_at).toLocaleDateString("ru-RU")}
                    </td>
                    <td className="px-3 py-3 align-top">{campaign.stats.transitions}</td>
                    <td className="px-3 py-3 align-top">{campaign.stats.bot_starts}</td>
                    <td className="px-3 py-3 align-top">{campaign.stats.trial_started}</td>
                    <td className="px-3 py-3 align-top">{campaign.stats.key_issued}</td>
                    <td className="px-3 py-3 align-top">{campaign.stats.paid}</td>
                    <td className="px-3 py-3 align-top">{campaign.stats.renewed}</td>
                    <td className="px-3 py-3 align-top">
                      <StatusBadge
                        status={campaign.stats.conversion_rate >= 10 ? "healthy" : campaign.stats.conversion_rate > 0 ? "warning" : "idle"}
                        label={`${campaign.stats.conversion_rate}%`}
                      />
                    </td>
                    <td className="px-3 py-3 align-top">
                      <div className="flex justify-end gap-2">
                        <Button variant="ghost" onClick={() => void copyToClipboard(campaign.tracking_url)}>
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() =>
                            replaceRouteParams((params) => {
                              params.set("campaign_id", String(campaign.id));
                            })
                          }
                        >
                          Детали
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-3">
            <EmptyState title="Кампаний пока нет" description="Создай первый tracking-token и используй его в постах и рекламе." />
          </div>
        )}
      </Card>

      {selectedCampaignId ? (
        <DetailPanel
          variant="overlay"
          title={detailQuery.data?.name || "Детали кампании"}
          subtitle={detailQuery.data ? `Token: ${detailQuery.data.token}` : "Загружаю детали…"}
          onClose={() =>
            replaceRouteParams((params) => {
              params.delete("campaign_id");
            })
          }
          actions={
            detailQuery.data ? (
              <Button variant="ghost" onClick={() => void copyToClipboard(detailQuery.data.tracking_url)}>
                <Copy className="mr-2 h-3.5 w-3.5" />
                Скопировать ссылку
              </Button>
            ) : null
          }
        >
          {detailQuery.isLoading ? (
            <PageLoader />
          ) : detailQuery.error || !detailQuery.data ? (
            <NoticeBanner tone="error">{detailQuery.error?.message || "Не удалось загрузить детали кампании"}</NoticeBanner>
          ) : (
            <div className="space-y-4">
              <Card className="space-y-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Трекинг-ссылка</div>
                <div className="rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[12px] text-slate-700 dark:text-slate-200">
                  {detailQuery.data.tracking_url}
                </div>
              </Card>

              <div className="grid gap-3 md:grid-cols-3">
                <MetricCard label="Переходы" value={detailQuery.data.stats.transitions} helper="link_touched" />
                <MetricCard label="Оплаты" value={detailQuery.data.stats.paid} helper="payment_success" />
                <MetricCard label="Конверсия" value={`${detailQuery.data.stats.conversion_rate}%`} helper="оплаты / переходы" />
              </div>

              <Card className="space-y-3">
                <div>
                  <h3 className="text-[14px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Воронка конверсии</h3>
                  <p className="text-[12px] leading-5 text-[color:var(--text-muted)]">
                    Быстрый срез по этапам: от касания ссылки до оплаты и продления.
                  </p>
                </div>
                <div className="space-y-3">
                  {detailQuery.data.funnel.map((stage) => (
                    <div key={stage.stage} className="space-y-1.5">
                      <div className="flex items-center justify-between gap-3 text-[13px]">
                        <span className="font-medium text-slate-900 dark:text-slate-100">{stage.stage}</span>
                        <span className="text-[color:var(--text-muted)]">
                          {stage.count} · {stage.rate}%
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-[var(--surface-strong)]">
                        <div
                          className="h-2 rounded-full bg-[linear-gradient(135deg,#0f4c81,#1098ad)]"
                          style={{ width: `${Math.max(0, Math.min(Number(stage.rate) || 0, 100))}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}
        </DetailPanel>
      ) : null}
    </div>
  );
}
