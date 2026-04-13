"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Card, Input, NoticeBanner, SectionHeading, Select, StatusBadge } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { usePromoCodes, useSession } from "@/hooks/use-dashboard";
import { apiPost } from "@/lib/api";
import { useToasts } from "@/components/toast-center";

export default function PromoCodesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const session = useSession();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [kindFilter, setKindFilter] = useState(searchParams.get("kind") || "all");
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || "all");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    code: "",
    kind: "discount_percent",
    title: "",
    description: "",
    discount_percent: "10",
    grant_days: "30",
    max_redemptions: "1",
    expires_at: "",
  });
  const [neverExpires, setNeverExpires] = useState(true);
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    setSearch(searchParams.get("q") || "");
    setKindFilter(searchParams.get("kind") || "all");
    setStatusFilter(searchParams.get("status") || "all");
  }, [searchParams]);

  const promoQuery = usePromoCodes(deferredSearch, kindFilter, statusFilter);
  const permissions = session.data?.admin.permissions ?? {};

  const replaceRouteParams = (mutate: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(searchParams.toString());
    mutate(params);
    router.replace(`/promocodes${params.toString() ? `?${params.toString()}` : ""}`);
  };

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost("/promocodes", payload),
    onSuccess: async () => {
      setError("");
      setNotice("Промокод создан.");
      await queryClient.invalidateQueries({ queryKey: ["promocodes"] });
      setForm((current) => ({ ...current, code: "", title: "", description: "" }));
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      pushToast({ title: "Не удалось создать промокод", description: mutationError.message, tone: "error" });
    },
  });

  if (promoQuery.isLoading) return <PageLoader />;
  if (promoQuery.error || !promoQuery.data) {
    return <PageError message={promoQuery.error?.message || "Не удалось загрузить промокоды"} />;
  }

  const summary = promoQuery.data.summary;
  const rows = promoQuery.data.codes;

  const canManagePromoCodes = Boolean(permissions.can_manage_payments);

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Промокоды"
        description="Управление скидками, кодами на дни доступа и подарочными кодами."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input
              id="promocodes-search"
              name="promocodesSearch"
              value={search}
              onChange={(event) => {
                const value = event.target.value;
                setSearch(value);
                replaceRouteParams((params) => {
                  if (value.trim()) params.set("q", value);
                  else params.delete("q");
                });
              }}
              placeholder="Код, описание, заголовок"
              className="w-full md:w-64"
            />
            <Select
              value={kindFilter}
              onChange={(event) => {
                const value = event.target.value;
                setKindFilter(value);
                replaceRouteParams((params) => {
                  if (value !== "all") params.set("kind", value);
                  else params.delete("kind");
                });
              }}
            >
              <option value="all">Все типы</option>
              <option value="discount_percent">Скидка</option>
              <option value="days_credit">Дни доступа</option>
              <option value="gift_days">Подарочные</option>
            </Select>
            <Select
              value={statusFilter}
              onChange={(event) => {
                const value = event.target.value;
                setStatusFilter(value);
                replaceRouteParams((params) => {
                  if (value !== "all") params.set("status", value);
                  else params.delete("status");
                });
              }}
            >
              <option value="all">Все статусы</option>
              <option value="active">Активные</option>
              <option value="inactive">Отключённые</option>
              <option value="exhausted">Исчерпанные</option>
            </Select>
          </div>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}

      <div className="grid gap-3 md:grid-cols-5">
        <Card className="space-y-1">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Всего</div>
          <div className="text-2xl font-semibold">{summary.total}</div>
        </Card>
        <Card className="space-y-1">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Активны</div>
          <div className="text-2xl font-semibold">{summary.active}</div>
        </Card>
        <Card className="space-y-1">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Скидки</div>
          <div className="text-2xl font-semibold">{summary.discounts}</div>
        </Card>
        <Card className="space-y-1">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Дни</div>
          <div className="text-2xl font-semibold">{summary.days}</div>
        </Card>
        <Card className="space-y-1">
          <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Подарочные / pending</div>
          <div className="text-2xl font-semibold">
            {summary.gift} / {summary.pending_discount_redemptions}
          </div>
        </Card>
      </div>

      <Card className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Генератор промокодов</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Можно создать код со скидкой в процентах, код на дни доступа или отдельный подарочный код.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="space-y-1">
            <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Код</div>
            <Input
              id="promo-code"
              name="promoCode"
              value={form.code}
              onChange={(event) => setForm((current) => ({ ...current, code: event.target.value.toUpperCase() }))}
              placeholder="AMONORA-SPRING"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Тип</div>
            <Select value={form.kind} onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value }))}>
              <option value="discount_percent">Скидка</option>
              <option value="days_credit">Дни доступа</option>
              <option value="gift_days">Подарочный код</option>
            </Select>
          </label>
          <label className="space-y-1">
            <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Заголовок</div>
            <Input
              id="promo-title"
              name="promoTitle"
              value={form.title}
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
              placeholder="Весеннее предложение"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Описание</div>
            <Input
              id="promo-description"
              name="promoDescription"
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Короткое описание для команды"
            />
          </label>
          {form.kind === "discount_percent" ? (
            <label className="space-y-1">
              <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Скидка, %</div>
              <Input
                id="promo-discount"
                name="promoDiscount"
                value={form.discount_percent}
                onChange={(event) => setForm((current) => ({ ...current, discount_percent: event.target.value }))}
                placeholder="10"
              />
            </label>
          ) : (
            <label className="space-y-1">
              <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Дней доступа</div>
              <Input
                id="promo-days"
                name="promoDays"
                value={form.grant_days}
                onChange={(event) => setForm((current) => ({ ...current, grant_days: event.target.value }))}
                placeholder="30"
              />
            </label>
          )}
          <label className="space-y-1">
            <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Лимит активаций</div>
            <Input
              id="promo-max-redemptions"
              name="promoMaxRedemptions"
              value={form.max_redemptions}
              onChange={(event) => setForm((current) => ({ ...current, max_redemptions: event.target.value }))}
              placeholder="1"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">Срок действия</div>
            <Input
              id="promo-expires-at"
              name="promoExpiresAt"
              type="datetime-local"
              value={form.expires_at}
              onChange={(event) => setForm((current) => ({ ...current, expires_at: event.target.value }))}
              disabled={neverExpires}
            />
            <label className="flex items-center gap-2 pt-1 text-sm text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={neverExpires}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  setNeverExpires(enabled);
                  if (enabled) {
                    setForm((current) => ({ ...current, expires_at: "" }));
                  }
                }}
              />
              <span>Бессрочный</span>
            </label>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            disabled={!canManagePromoCodes || createMutation.isPending}
            onClick={() => {
              setNotice("");
              setError("");
              createMutation.mutate({
                code: form.code.trim(),
                kind: form.kind,
                title: form.title.trim(),
                description: form.description.trim(),
                discount_percent: form.kind === "discount_percent" ? Number(form.discount_percent || 0) : null,
                grant_days: form.kind === "discount_percent" ? null : Number(form.grant_days || 0),
                max_redemptions: Number(form.max_redemptions || 1),
                expires_at: neverExpires || !form.expires_at ? null : new Date(form.expires_at).toISOString(),
              });
            }}
          >
            Создать промокод
          </Button>
          {!canManagePromoCodes ? (
            <span className="text-sm text-rose-500">Недостаточно прав для создания промокодов.</span>
          ) : null}
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-[0.14em] text-slate-500 dark:bg-slate-900/40 dark:text-slate-400">
              <tr>
                <th className="px-4 py-3">Код</th>
                <th className="px-4 py-3">Тип</th>
                <th className="px-4 py-3">Условия</th>
                <th className="px-4 py-3">Статус</th>
                <th className="px-4 py-3">Активации</th>
                <th className="px-4 py-3">Подарок / покупатель</th>
                <th className="px-4 py-3">Истекает</th>
                <th className="px-4 py-3">Создан</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-slate-200/70 dark:border-slate-800">
                  <td className="px-4 py-3 align-top">
                    <div className="font-medium text-slate-900 dark:text-slate-100">{row.code}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{row.title}</div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{row.description}</div>
                  </td>
                  <td className="px-4 py-3 align-top">{row.kind_label}</td>
                  <td className="px-4 py-3 align-top">
                    {row.discount_percent ? `Скидка ${row.discount_percent}%` : `Доступ на ${row.grant_days} дн.`}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <StatusBadge status={row.status} label={row.status_label} />
                  </td>
                  <td className="px-4 py-3 align-top">
                    {row.redeemed_count} / {row.max_redemptions}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <div>{row.kind === "gift_days" ? "Да" : "Нет"}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{row.buyer_label}</div>
                  </td>
                  <td className="px-4 py-3 align-top">{row.expires_at || "—"}</td>
                  <td className="px-4 py-3 align-top">
                    <div>{row.created_at}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{row.created_by_name}</div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500 dark:text-slate-400">
                    Промокоды пока не найдены.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
