"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, NoticeBanner, SectionHeading } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useTraffic } from "@/hooks/use-dashboard";
import { apiPost } from "@/lib/api";
import { useToasts } from "@/components/toast-center";

function formatTransfer(value: number) {
  const numeric = Number(value || 0);
  if (!numeric) return "0 MB";
  if (numeric >= 1) return `${numeric.toFixed(2)} GB`;
  return `${(numeric * 1024).toFixed(numeric >= 0.1 ? 0 : 1)} MB`;
}

function formatThroughput(value: number) {
  const numeric = Number(value || 0);
  if (!numeric) return "0 Мбит/с";
  if (numeric >= 1000) return `${(numeric / 1000).toFixed(2)} Гбит/с`;
  return `${numeric >= 10 ? numeric.toFixed(1) : numeric.toFixed(2)} Мбит/с`;
}

function confirmAction(message: string): boolean {
  if (typeof window === "undefined") return true;
  return window.confirm(message);
}

function formatProtocolMix(rows: Array<{ label: string; value: number }>) {
  if (!rows.length) return "Нет данных";
  return rows
    .map((item) => `${item.label}: ${item.value}`)
    .join(" · ");
}

function estimateTransfer(total: number, baselineResetAt?: string | null, periodDays = 1) {
  if (!total) return 0;
  if (!baselineResetAt) return Number(((total / 30) * periodDays).toFixed(3));
  const parsed = Date.parse(baselineResetAt);
  if (Number.isNaN(parsed)) return Number(((total / 30) * periodDays).toFixed(3));
  const days = Math.max((Date.now() - parsed) / 86_400_000, 1);
  const perDay = total / days;
  return Number((perDay * periodDays).toFixed(2));
}

export default function TrafficPage() {
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const query = useTraffic();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const resetMutation = useMutation({
    mutationFn: () => apiPost("/traffic/reset"),
    onSuccess: async () => {
      setError("");
      setNotice("Накопленный трафик сброшен. Новый отсчёт начался с текущего момента.");
      pushToast({ title: "Трафик сброшен", description: "Новый отсчёт уже начался.", tone: "success" });
      await queryClient.invalidateQueries({ queryKey: ["traffic"] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      pushToast({ title: "Сброс не выполнен", description: mutationError.message, tone: "error" });
    },
  });

  if (query.isLoading) return <PageLoader />;
  if (query.error || !query.data) {
    return <PageError message={query.error?.message || "Не удалось загрузить трафик"} />;
  }

  const { overview, connections_by_region, protocol_mix, load_by_server, bandwidth_by_server } = query.data;
  const topNode = [...bandwidth_by_server].sort((left, right) => right.traffic - left.traffic)[0];
  const peakActivity = [...query.data.peak_hours].sort((left, right) => right.activity - left.activity)[0];
  const regionMap = new Map(connections_by_region.map((item) => [item.region, item.connections]));
  const averageCpu = load_by_server?.length
    ? Math.round(load_by_server.reduce((total, item) => total + Number(item.cpu || 0), 0) / load_by_server.length)
    : 0;
  const averageRam = load_by_server?.length
    ? Math.round(load_by_server.reduce((total, item) => total + Number(item.ram || 0), 0) / load_by_server.length)
    : 0;
  const averageDisk = load_by_server?.length
    ? Math.round(load_by_server.reduce((total, item) => total + Number(item.disk || 0), 0) / load_by_server.length)
    : 0;

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Трафик"
        description="Сетевой срез без лишних графиков."
        actions={
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              if (!confirmAction("Сбросить накопленный baseline трафика? Live throughput при этом не обнулится.")) {
                return;
              }
              resetMutation.mutate();
            }}
            disabled={resetMutation.isPending}
          >
            Сбросить накопленный трафик
          </Button>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}
      {overview.baseline_reset_at ? (
        <NoticeBanner tone="info">Накопленный трафик считается от {overview.baseline_reset_at}. С 1-го числа месяца baseline сбрасывается автоматически, live throughput и нагрузка нод при этом не обнуляются.</NoticeBanner>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-2">
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Трафик</div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div>
              <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">С начала периода</div>
              <div className="mt-1 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
                {formatTransfer(overview.total_transfer_gb)}
              </div>
            </div>
            <div>
              <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Среднее за сутки</div>
              <div className="mt-1 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
                {formatTransfer(estimateTransfer(overview.total_transfer_gb, overview.baseline_reset_at, 1))}
              </div>
            </div>
            <div>
              <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Прогноз на 30 дней</div>
              <div className="mt-1 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
                {formatTransfer(estimateTransfer(overview.total_transfer_gb, overview.baseline_reset_at, 30))}
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Устройства по регионам</div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div>
              <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Германия</div>
              <div className="mt-1 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{regionMap.get("Германия") || 0}</div>
            </div>
            <div>
              <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Дания</div>
              <div className="mt-1 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{regionMap.get("Дания") || 0}</div>
            </div>
            <div>
              <div className="text-[12px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Эстония</div>
              <div className="mt-1 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{regionMap.get("Эстония") || 0}</div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid gap-3 xl:grid-cols-4">
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Live throughput</div>
          <div className="mt-2 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{formatThroughput(overview.current_bandwidth)}</div>
          <div className="mt-1 text-[13px] text-[color:var(--text-muted)]">Нод с отчётом: {overview.servers_reporting}</div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Control-plane activity</div>
          <div className="mt-2 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{peakActivity?.activity || 0}</div>
          <div className="mt-1 text-[13px] text-[color:var(--text-muted)]">Пик: {peakActivity?.hour || "—"}</div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Protocol mix</div>
          <div className="mt-2 text-[13px] font-semibold leading-5 text-slate-950 dark:text-slate-50">{formatProtocolMix(protocol_mix || [])}</div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Load profile</div>
          <div className="mt-2 text-[13px] font-semibold leading-5 text-slate-950 dark:text-slate-50">
            CPU {averageCpu}% · RAM {averageRam}% · Память {averageDisk}%
          </div>
          <div className="mt-1 text-[13px] text-[color:var(--text-muted)]">Нода: {topNode?.server || "—"}</div>
        </Card>
      </div>
    </div>
  );
}
