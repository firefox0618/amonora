"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MouseEvent, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Card, DetailPanel, EmptyState, Input, NoticeBanner, SectionHeading, Select, StatusBadge } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { usePayments, useSession } from "@/hooks/use-dashboard";
import { apiPost } from "@/lib/api";
import { describeRepairResult } from "@/lib/repair-feedback";
import { FinanceEntry, UserVpnRepairActionResult } from "@/lib/types";
import { useToasts } from "@/components/toast-center";
import { formatRub } from "@/lib/utils";

const ENTRY_TONE: Record<string, string> = {
  income: "text-emerald-700 dark:text-emerald-300",
  expense: "text-rose-700 dark:text-rose-300",
  salary: "text-rose-700 dark:text-rose-300",
  settlement: "text-amber-700 dark:text-amber-300",
  transfer: "text-blue-700 dark:text-blue-300",
  adjustment: "text-slate-700 dark:text-slate-200",
};

export default function PaymentsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const session = useSession();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || "all");
  const [methodFilter, setMethodFilter] = useState(searchParams.get("method") || "all");
  const [issueFilter, setIssueFilter] = useState(searchParams.get("issue") || "all");
  const [periodKey, setPeriodKey] = useState(searchParams.get("period_key") || "");
  const [selectedRecordId, setSelectedRecordId] = useState<number | undefined>(
    searchParams.get("record_id") ? Number(searchParams.get("record_id")) : undefined,
  );
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [paymentForm, setPaymentForm] = useState({
    user_id: "",
    payment_method: "sbp_manual",
    tariff_code: "1m",
    payment_status: "awaiting_admin_review",
    reference: "",
    note: "",
  });
  const [financeForm, setFinanceForm] = useState({
    entry_type: "expense",
    category: "operations",
    amount: "",
    note: "",
    related_server: "",
    status: "draft",
    counterparty_admin_id: "",
    occurred_at: "",
  });
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    setSearch(searchParams.get("q") || "");
    setStatusFilter(searchParams.get("status") || "all");
    setMethodFilter(searchParams.get("method") || "all");
    setIssueFilter(searchParams.get("issue") || "all");
    setPeriodKey(searchParams.get("period_key") || "");
    setSelectedRecordId(searchParams.get("record_id") ? Number(searchParams.get("record_id")) : undefined);
  }, [searchParams]);

  const paymentsQuery = usePayments(
    selectedRecordId,
    periodKey || undefined,
    deferredSearch,
    statusFilter,
    methodFilter,
    issueFilter,
  );
  const permissions = session.data?.admin.permissions ?? {};
  const paymentsData = paymentsQuery.data;
  const summary = paymentsData?.summary ?? {
    mrr: 0,
    new_subscriptions: 0,
    refunds: 0,
    failed_payments: 0,
    manual_queue: 0,
    awaiting_payment: 0,
    confirmed: 0,
    expired: 0,
    disputed: 0,
    error: 0,
    problem_records: 0,
  };
  const records = Array.isArray(paymentsData?.records) ? paymentsData.records : [];
  const finance = paymentsData?.finance ?? {
    summary: {},
    dashboard: { summary: {}, entries: [], selected_entry: null, periods: [], admins: [], filters: {}, recurring_rows: [] },
  };
  const financeDashboard = finance.dashboard ?? { summary: {}, entries: [], selected_entry: null, periods: [], admins: [], filters: {}, recurring_rows: [] };
  const tariffs = Array.isArray(paymentsData?.tariffs) ? paymentsData.tariffs : [];
  const selectedRecord =
    selectedRecordId !== undefined ? paymentsData?.selected_record ?? records.find((record) => record.id === selectedRecordId) ?? null : null;
  const financeEntries = Array.isArray(financeDashboard.entries) ? financeDashboard.entries : [];
  const financeSummary = (finance.summary ?? {}) as {
    income?: number;
    expense?: number;
    net?: number;
  };
  const activePeriodKey = String(periodKey || financeDashboard.filters?.period_key || "");

  const mutation = useMutation({
    mutationFn: (payload: { path: string; body?: unknown }) => apiPost(payload.path, payload.body),
    onSuccess: async () => {
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["payments"] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      pushToast({ title: "Операция не выполнена", description: mutationError.message, tone: "error" });
    },
  });

  const recentFinanceEntries = financeEntries.slice(0, 14);
  const filteredRecords = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    return records.filter((record) => {
      if (statusFilter !== "all" && record.payment_status !== statusFilter) return false;
      if (methodFilter !== "all" && record.payment_method !== methodFilter) return false;
      if (issueFilter !== "all") {
        if (issueFilter === "review" && !record.is_reviewable) return false;
        if (issueFilter === "waiting" && !record.is_waiting_user) return false;
        if (issueFilter === "problem" && !["rejected", "expired", "disputed", "error", "cancelled"].includes(record.payment_status)) return false;
        if (issueFilter === "confirmed" && record.payment_status !== "confirmed") return false;
      }
      if (!query) return true;
      const haystack = [
        String(record.id),
        record.username || "",
        String(record.telegram_id || ""),
        record.tariff_code || "",
        record.payment_method_label || "",
        record.reference || "",
        record.note || "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [deferredSearch, issueFilter, methodFilter, records, statusFilter]);

  if (paymentsQuery.isLoading) return <PageLoader />;
  if (paymentsQuery.error || !paymentsData) {
    return <PageError message={paymentsQuery.error?.message || "Не удалось загрузить финансы"} />;
  }

  const tariffOptions = tariffs
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      code: String(item.code || ""),
      title: String(item.title || item.code || ""),
    }));

  const paymentStatusActions = [
    { value: "confirmed", label: "Подтвердить", variant: "primary" as const },
    { value: "rejected", label: "Отклонить", variant: "danger" as const },
    { value: "expired", label: "Истек", variant: "ghost" as const },
    { value: "disputed", label: "Спорный", variant: "secondary" as const },
    { value: "error", label: "Ошибка", variant: "ghost" as const },
  ];

  const canReviewSelectedRecord = Boolean(
    selectedRecord?.is_reviewable && selectedRecord?.payment_status === "awaiting_admin_review",
  );
  const allowedStatusActions = new Set(selectedRecord?.available_status_actions ?? []);
  const visibleStatusActions = paymentStatusActions.filter((item) => {
    if (!allowedStatusActions.has(item.value)) return false;
    if (canReviewSelectedRecord && (item.value === "confirmed" || item.value === "rejected")) return false;
    return true;
  });

  const openPayment = (recordId: number) => {
    setSelectedRecordId(recordId);
    replaceRouteParams((params) => {
      params.set("record_id", String(recordId));
    });
  };

  const stopActionClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const confirmAction = (message: string) => {
    if (typeof window === "undefined") return true;
    return window.confirm(message);
  };

  const resetFinanceForm = () =>
    setFinanceForm({
      entry_type: "expense",
      category: "operations",
      amount: "",
      note: "",
      related_server: "",
      status: "draft",
      counterparty_admin_id: "",
      occurred_at: "",
    });

  const replaceRouteParams = (mutate: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(searchParams.toString());
    mutate(params);
    router.replace(`/payments${params.toString() ? `?${params.toString()}` : ""}`);
  };

  const updateRouteParam = (key: string, value: string) => {
    replaceRouteParams((params) => {
      if (value && value !== "all") params.set(key, value);
      else params.delete(key);
    });
  };

  const refreshPayments = async () => {
    setNotice("");
    setError("");
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["payments"] }),
      queryClient.invalidateQueries({ queryKey: ["overview"] }),
      queryClient.invalidateQueries({ queryKey: ["users"] }),
      queryClient.invalidateQueries({ queryKey: ["support"] }),
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    ]);
    setNotice("Данные обновлены.");
  };

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Финансы"
        description="Платежи и операционные записи."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input
              id="payments-search"
              name="paymentsSearch"
              value={search}
              onChange={(event) => {
                const value = event.target.value;
                setSearch(value);
                replaceRouteParams((params) => {
                  if (value.trim()) params.set("q", value);
                  else params.delete("q");
                });
              }}
              placeholder="ID, TG, ник, ref"
              className="w-full md:w-56"
            />
            <Select
              id="payments-status-filter"
              name="paymentsStatusFilter"
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value);
                updateRouteParam("status", event.target.value);
              }}
            >
              <option value="all">Статус</option>
              <option value="pending">Ожидает провайдера</option>
              <option value="awaiting_admin_review">На проверке</option>
              <option value="awaiting_user_payment">Ждёт оплату</option>
              <option value="confirmed">Подтверждён</option>
              <option value="rejected">Отклонён</option>
              <option value="expired">Истёк</option>
              <option value="disputed">Спорный</option>
              <option value="error">Ошибка</option>
            </Select>
            <Select
              id="payments-method-filter"
              name="paymentsMethodFilter"
              value={methodFilter}
              onChange={(event) => {
                setMethodFilter(event.target.value);
                updateRouteParam("method", event.target.value);
              }}
            >
              <option value="all">Метод</option>
              <option value="sbp_platega">СБП (Platega)</option>
              <option value="crypto_platega">Криптовалюта (Platega)</option>
              <option value="sbp_manual">Ручная СБП</option>
              <option value="crypto_manual">Ручная крипта</option>
              <option value="telegram_stars">Telegram Stars</option>
              <option value="crypto_bot">Crypto Bot</option>
            </Select>
            <Select
              id="payments-issue-filter"
              name="paymentsIssueFilter"
              value={issueFilter}
              onChange={(event) => {
                setIssueFilter(event.target.value);
                updateRouteParam("issue", event.target.value);
              }}
            >
              <option value="all">Срез</option>
              <option value="review">Ждут проверки</option>
              <option value="waiting">Ждут оплату</option>
              <option value="problem">Проблемные</option>
              <option value="confirmed">Подтверждённые</option>
            </Select>
            <Select
              id="payments-period-filter"
              name="paymentsPeriodFilter"
              value={activePeriodKey}
              onChange={(event) => {
                setPeriodKey(event.target.value);
                updateRouteParam("period_key", event.target.value);
              }}
            >
              {(financeDashboard.periods || []).map((item: string) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
            <Button type="button" variant="ghost" onClick={() => void refreshPayments()}>
              Обновить
            </Button>
          </div>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}

      <div className="grid gap-3 xl:grid-cols-4">
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Выручка</div>
          <div className="mt-2 text-[1.35rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            {formatRub(summary.mrr)} / {formatRub(financeSummary.income ?? 0)}
          </div>
          <div className="mt-1 text-[13px] text-[color:var(--text-muted)]">
            30 дней по Platega СБП и крипте / доходы периода {activePeriodKey || "—"}
          </div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Очередь / подтверждено</div>
          <div className="mt-2 text-[1.35rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            {summary.manual_queue || 0} / {summary.confirmed || 0}
          </div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Проблемные / ждут оплату</div>
          <div className="mt-2 text-[1.35rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">
            {summary.problem_records || 0} / {summary.awaiting_payment || 0}
          </div>
        </Card>
        <Card>
          <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Доходы / расходы / взаимозачёты</div>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[13px] font-semibold">
            <span className="text-emerald-700 dark:text-emerald-300">{formatRub(financeSummary.income ?? 0)}</span>
            <span className="text-rose-700 dark:text-rose-300">{formatRub(financeSummary.expense ?? 0)}</span>
            <span className="text-amber-700 dark:text-amber-300">{formatRub(financeSummary.net ?? 0)}</span>
          </div>
        </Card>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="grid grid-cols-[0.75fr_0.95fr_1fr_0.85fr_0.9fr_0.8fr_0.8fr] gap-3 border-b border-[color:var(--surface-border)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          <span>№ транзакции</span>
          <span>Дата</span>
          <span>Пользователь</span>
          <span>Тариф</span>
          <span>Метод</span>
          <span>Стоимость</span>
          <span>Статус</span>
        </div>
        <div className="divide-y divide-[color:var(--surface-border)]">
          {filteredRecords.length ? (
            filteredRecords.map((record) => (
              <button
                key={record.id}
                type="button"
                onClick={() => openPayment(record.id)}
                className={`grid w-full cursor-pointer grid-cols-[0.75fr_0.95fr_1fr_0.85fr_0.9fr_0.8fr_0.8fr] gap-3 px-4 py-3 text-left transition hover:bg-white/35 dark:hover:bg-white/4 ${
                  selectedRecord?.id === record.id ? "bg-white/40 dark:bg-white/4" : ""
                }`}
              >
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">#{record.id}</div>
                <div className="text-[13px] text-[color:var(--text-muted)]">{record.created_at}</div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-semibold text-slate-950 dark:text-slate-50">{record.username}</div>
                  <div className="truncate text-[13px] text-[color:var(--text-muted)]">{record.telegram_id || "—"}</div>
                </div>
                <div className="text-[13px] text-slate-700 dark:text-slate-300">{record.tariff_label || record.tariff_code}</div>
                <div className="text-[13px] text-slate-700 dark:text-slate-300">{record.payment_method_label}</div>
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatRub(record.amount)}</div>
                <StatusBadge status={record.payment_status} label={record.payment_status_label} />
              </button>
            ))
          ) : (
            <div className="px-5 py-10">
              <EmptyState title="Платежей нет" description="Когда появятся заявки, здесь будет живая очередь." />
            </div>
          )}
        </div>
      </Card>

      <Card className="overflow-hidden p-0">
        <div className="grid grid-cols-[0.7fr_1fr_0.7fr_0.9fr_1.2fr_0.7fr] gap-3 border-b border-[color:var(--surface-border)] px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">
          <span>№</span>
          <span>Операция</span>
          <span>Сумма</span>
          <span>Дата</span>
          <span>Комментарий</span>
          <span>Статус</span>
        </div>
        <div className="divide-y divide-[color:var(--surface-border)]">
          {recentFinanceEntries.length ? (
            recentFinanceEntries.map((entry: FinanceEntry) => (
              <div key={entry.id} className="grid grid-cols-[0.7fr_1fr_0.7fr_0.9fr_1.2fr_0.7fr] gap-3 px-4 py-3 text-[13px]">
                <div className="font-semibold text-slate-950 dark:text-slate-50">#{entry.id}</div>
                <div className={ENTRY_TONE[entry.entry_type] || "text-slate-700 dark:text-slate-200"}>{entry.entry_type_label}</div>
                <div className={`font-semibold ${ENTRY_TONE[entry.entry_type] || "text-slate-950 dark:text-slate-50"}`}>{formatRub(entry.signed_amount)}</div>
                <div className="text-[color:var(--text-muted)]">{entry.occurred_at}</div>
                <div className="truncate text-[color:var(--text-muted)]">{entry.note || entry.related_server || "—"}</div>
                <StatusBadge status={entry.status} label={entry.status_label} />
              </div>
            ))
          ) : (
            <div className="px-4 py-8 text-[13px] text-[color:var(--text-muted)]">Операционных записей пока нет.</div>
          )}
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="space-y-3">
          <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Новая manual / emergency заявка</div>
          <Input id="payment-user-id" name="paymentUserId" placeholder="User ID" value={paymentForm.user_id} onChange={(event) => setPaymentForm((prev) => ({ ...prev, user_id: event.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <Select id="payment-method" name="paymentMethod" value={paymentForm.payment_method} onChange={(event) => setPaymentForm((prev) => ({ ...prev, payment_method: event.target.value }))}>
              <option value="sbp_manual">Ручная СБП</option>
              <option value="crypto_manual">Ручная крипта</option>
            </Select>
            <Select id="payment-tariff-code" name="paymentTariffCode" value={paymentForm.tariff_code} onChange={(event) => setPaymentForm((prev) => ({ ...prev, tariff_code: event.target.value }))}>
              {tariffOptions.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.title}
                </option>
              ))}
            </Select>
          </div>
          <Select id="payment-status" name="paymentStatus" value={paymentForm.payment_status} onChange={(event) => setPaymentForm((prev) => ({ ...prev, payment_status: event.target.value }))}>
            <option value="awaiting_user_payment">Ожидает оплату</option>
            <option value="awaiting_admin_review">На проверке</option>
            <option value="confirmed">Сразу подтверждён</option>
            <option value="rejected">Отклонён</option>
            <option value="expired">Истёк</option>
            <option value="disputed">Спорный</option>
            <option value="error">Ошибка</option>
          </Select>
          <Input id="payment-reference" name="paymentReference" placeholder="Reference" value={paymentForm.reference} onChange={(event) => setPaymentForm((prev) => ({ ...prev, reference: event.target.value }))} />
          <Input id="payment-note" name="paymentNote" placeholder="Комментарий" value={paymentForm.note} onChange={(event) => setPaymentForm((prev) => ({ ...prev, note: event.target.value }))} />
          <Button
            type="button"
            disabled={mutation.isPending || !permissions.can_manage_payments}
            onClick={(event) => {
              stopActionClick(event);
              if (!confirmAction(`Создать новую ручную заявку для пользователя #${paymentForm.user_id || "?"}?`)) {
                return;
              }
              mutation.mutate(
                {
                  path: "/payments",
                  body: {
                    ...paymentForm,
                    user_id: paymentForm.user_id.trim() ? Number(paymentForm.user_id) : null,
                  },
                },
                {
                  onSuccess: async () => {
                    setNotice("Новая заявка добавлена.");
                    pushToast({ title: "Заявка создана", description: "Запись появилась в очереди.", tone: "success" });
                    await queryClient.invalidateQueries({ queryKey: ["payments"] });
                  },
                },
              );
            }}
          >
            Новая заявка / запись
          </Button>
        </Card>

        <Card className="space-y-3">
          <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Добавить операционную запись</div>
          <div className="grid grid-cols-2 gap-2">
            <Select id="finance-entry-type" name="financeEntryType" value={financeForm.entry_type} onChange={(event) => setFinanceForm((prev) => ({ ...prev, entry_type: event.target.value }))}>
              <option value="expense">Расход</option>
              <option value="income">Доход</option>
              <option value="salary">Зарплата</option>
              <option value="settlement">Взаимозачёт</option>
              <option value="transfer">Перевод</option>
              <option value="adjustment">Корректировка</option>
            </Select>
            <Select id="finance-status" name="financeStatus" value={financeForm.status} onChange={(event) => setFinanceForm((prev) => ({ ...prev, status: event.target.value }))}>
              <option value="draft">Черновик</option>
              <option value="posted">Проведено</option>
            </Select>
          </div>
          <Select id="finance-category" name="financeCategory" value={financeForm.category} onChange={(event) => setFinanceForm((prev) => ({ ...prev, category: event.target.value }))}>
            <option value="operations">Операционные</option>
            <option value="server">Сервер</option>
            <option value="domain">Домен</option>
            <option value="salary">Зарплата</option>
            <option value="settlement">Взаимозачёт</option>
            <option value="adjustment">Корректировка</option>
          </Select>
          <Input id="finance-amount" name="financeAmount" placeholder="Сумма в RUB" value={financeForm.amount} onChange={(event) => setFinanceForm((prev) => ({ ...prev, amount: event.target.value }))} />
          <Input id="finance-related-server" name="financeRelatedServer" placeholder="Сервер / домен / сервис" value={financeForm.related_server} onChange={(event) => setFinanceForm((prev) => ({ ...prev, related_server: event.target.value }))} />
          <Select id="finance-counterparty-admin" name="financeCounterpartyAdminId" value={financeForm.counterparty_admin_id} onChange={(event) => setFinanceForm((prev) => ({ ...prev, counterparty_admin_id: event.target.value }))}>
            <option value="">Контрагент не выбран</option>
            {(Array.isArray(financeDashboard.admins) ? financeDashboard.admins : []).map((admin) => (
              <option key={admin.id} value={admin.id}>
                {admin.display_name} · {admin.role_name}
              </option>
            ))}
          </Select>
          <Input id="finance-occurred-at" name="financeOccurredAt" type="datetime-local" value={financeForm.occurred_at} onChange={(event) => setFinanceForm((prev) => ({ ...prev, occurred_at: event.target.value }))} />
          <Input id="finance-note" name="financeNote" placeholder="Комментарий" value={financeForm.note} onChange={(event) => setFinanceForm((prev) => ({ ...prev, note: event.target.value }))} />
          <Button
            type="button"
            disabled={mutation.isPending || !permissions.can_manage_finance}
            onClick={(event) => {
              stopActionClick(event);
              if (!confirmAction(`Добавить операционную запись на ${financeForm.amount || "0"} ₽ в категорию «${financeForm.category}»?`)) {
                return;
              }
              mutation.mutate(
                {
                  path: "/finance",
                  body: {
                    ...financeForm,
                    amount: Number(financeForm.amount || 0),
                    counterparty_admin_id: financeForm.counterparty_admin_id ? Number(financeForm.counterparty_admin_id) : null,
                  },
                },
                {
                  onSuccess: async () => {
                    resetFinanceForm();
                    setNotice("Финансовая запись добавлена.");
                    pushToast({ title: "Запись добавлена", description: financeForm.category, tone: "success" });
                    await queryClient.invalidateQueries({ queryKey: ["payments"] });
                  },
                },
              );
            }}
          >
            Добавить операционную запись
          </Button>
        </Card>
      </div>

      {selectedRecord ? (
        <DetailPanel
          variant="overlay"
          className="max-w-[980px]"
          bodyClassName="space-y-4"
          title={`Транзакция #${selectedRecord.id}`}
          subtitle={`${selectedRecord.username} · ${selectedRecord.created_at}`}
          onClose={() => {
            setSelectedRecordId(undefined);
            replaceRouteParams((params) => {
              params.delete("record_id");
            });
          }}
        >
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_300px]">
            <div className="space-y-4">
              <Card className="space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Пользователь</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.username}</div></div>
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Telegram ID</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.telegram_id || "—"}</div></div>
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Тариф</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.tariff_label || selectedRecord.tariff_code}</div></div>
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Метод</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.payment_method_label}</div></div>
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Стоимость</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{formatRub(selectedRecord.amount)}</div></div>
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Статус</div><div className="mt-1"><StatusBadge status={selectedRecord.payment_status} label={selectedRecord.payment_status_label} /></div></div>
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Дата</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.created_at}</div></div>
                  <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Подтверждено</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.confirmed_at}</div></div>
                  {selectedRecord.provider_name ? (
                    <>
                      <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Провайдер</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.provider_name}</div></div>
                      <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Provider status</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.provider_status || "—"}</div></div>
                      <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Transaction ID</div><div className="mt-1 break-all text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.provider_transaction_id || "—"}</div></div>
                      <div><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Последняя sync</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.last_provider_sync_at || "—"}</div></div>
                    </>
                  ) : null}
                  <div className="md:col-span-2"><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Комментарий</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.note || "—"}</div></div>
                  <div className="md:col-span-2"><div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">Reference</div><div className="mt-1 text-[13px] font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.reference || "—"}</div></div>
                </div>
                {selectedRecord.checkout_url ? (
                  <a
                    href={selectedRecord.checkout_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex w-full items-center justify-center rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[11px] font-medium text-slate-700 transition hover:border-[color:var(--accent)] hover:bg-white hover:text-slate-950 dark:bg-[var(--surface-muted)] dark:text-slate-200 dark:hover:bg-[rgba(27,35,46,0.96)] dark:hover:text-white"
                  >
                    Открыть страницу оплаты
                  </a>
                ) : null}
                {selectedRecord.rejection_reason ? (
                  <div className="rounded-[10px] border border-rose-300/60 bg-rose-50/60 px-3 py-2 text-[11px] text-rose-800 dark:border-rose-700/50 dark:bg-rose-950/20 dark:text-rose-200">
                    Причина отклонения: {selectedRecord.rejection_reason}
                  </div>
                ) : null}
                {selectedRecord.provider_sync_problem ? (
                  <div className="rounded-[10px] border border-amber-300/60 bg-amber-50/60 px-3 py-2 text-[11px] text-amber-900 dark:border-amber-700/50 dark:bg-amber-950/20 dark:text-amber-200">
                    Внимание провайдера: {selectedRecord.provider_sync_problem}
                  </div>
                ) : null}
              </Card>

              {selectedRecord.linked_user_context ? (
                <Card className="space-y-2">
                  <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Связанный контекст</div>
                  <div className="grid gap-2 text-[11px]">
                    <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">Пользователь</span><span className="font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.linked_user_context.username}</span></div>
                    <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">Доступ</span><StatusBadge status={selectedRecord.linked_user_context.status_state} label={selectedRecord.linked_user_context.status_label || selectedRecord.linked_user_context.access_status} /></div>
                    <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">До</span><span className="font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.linked_user_context.access_expires_at}</span></div>
                    <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">Устройства</span><span className="font-semibold text-slate-950 dark:text-slate-50">{selectedRecord.linked_user_context.devices_count} / {selectedRecord.linked_user_context.max_devices || 3}</span></div>
                  </div>
                </Card>
              ) : null}
            </div>

            <div className="space-y-3">
              <Card className="space-y-2">
                <div className="text-[13px] font-semibold text-slate-950 dark:text-slate-50">Действия</div>
                <div className="grid gap-2">
                  {selectedRecord.can_send_reminder ? (
                    <Button
                      type="button"
                      className="justify-start"
                      disabled={mutation.isPending || !permissions.can_manage_payments}
                      onClick={(event) => {
                        stopActionClick(event);
                        if (!confirmAction(`Отправить напоминание пользователю по платежу #${selectedRecord.id}?`)) {
                          return;
                        }
                        mutation.mutate(
                          { path: `/payments/${selectedRecord.id}/remind` },
                          {
                            onSuccess: async () => {
                              setNotice(`Напоминание по платежу #${selectedRecord.id} отправлено пользователю.`);
                              pushToast({ title: "Напоминание отправлено", description: `#${selectedRecord.id}`, tone: "info" });
                              await queryClient.invalidateQueries({ queryKey: ["payments"] });
                            },
                          },
                        );
                      }}
                    >
                      Напомнить об оплате
                    </Button>
                  ) : null}
                  {selectedRecord.can_sync_provider ? (
                    <Button
                      type="button"
                      className="justify-start"
                      disabled={mutation.isPending || !permissions.can_manage_payments}
                      onClick={(event) => {
                        stopActionClick(event);
                        if (!confirmAction(`Синхронизировать платёж #${selectedRecord.id} с провайдером прямо сейчас?`)) {
                          return;
                        }
                        mutation.mutate(
                          { path: `/payments/${selectedRecord.id}/sync` },
                          {
                            onSuccess: async () => {
                              setNotice(`Платёж #${selectedRecord.id} синхронизирован с провайдером.`);
                              pushToast({ title: "Синхронизация выполнена", description: `#${selectedRecord.id}`, tone: "success" });
                              await queryClient.invalidateQueries({ queryKey: ["payments"] });
                            },
                          },
                        );
                      }}
                    >
                      Синхронизировать оплату
                    </Button>
                  ) : null}
                  {canReviewSelectedRecord ? (
                    <>
                      <Button
                        type="button"
                        className="justify-start"
                        disabled={mutation.isPending || !permissions.can_manage_payments}
                      onClick={(event) => {
                        stopActionClick(event);
                        if (!confirmAction(`Подтвердить платёж #${selectedRecord.id}? Доступ или продуктовый эффект может примениться сразу.`)) {
                          return;
                        }
                        mutation.mutate(
                          { path: `/payments/${selectedRecord.id}/confirm` },
                            {
                              onSuccess: async () => {
                                setNotice(`Платёж #${selectedRecord.id} подтверждён.`);
                                pushToast({ title: "Платёж подтверждён", description: `#${selectedRecord.id}`, tone: "success" });
                                await queryClient.invalidateQueries({ queryKey: ["payments"] });
                              },
                            },
                          );
                        }}
                      >
                        Подтвердить
                      </Button>
                      <Button
                        type="button"
                        variant="danger"
                        className="justify-start"
                        disabled={mutation.isPending || !permissions.can_manage_payments}
                      onClick={(event) => {
                        stopActionClick(event);
                        if (!confirmAction(`Отклонить платёж #${selectedRecord.id}? Пользователь не получит доступ по этой заявке.`)) {
                          return;
                        }
                        mutation.mutate(
                          { path: `/payments/${selectedRecord.id}/reject`, body: { reason: "Отклонено из панели" } },
                            {
                              onSuccess: async () => {
                                setNotice(`Платёж #${selectedRecord.id} отклонён.`);
                                pushToast({ title: "Платёж отклонён", description: `#${selectedRecord.id}`, tone: "warning" });
                                await queryClient.invalidateQueries({ queryKey: ["payments"] });
                              },
                            },
                          );
                        }}
                      >
                        Отклонить
                      </Button>
                    </>
                  ) : null}
                  {visibleStatusActions.map((item) => (
                    <Button
                      key={item.value}
                      type="button"
                      variant={item.variant}
                      className="justify-start"
                      disabled={mutation.isPending || !permissions.can_manage_payments}
                      onClick={(event) => {
                        stopActionClick(event);
                        if (!confirmAction(`Изменить статус платежа #${selectedRecord.id} на «${item.label}»?`)) {
                          return;
                        }
                        mutation.mutate(
                          { path: `/payments/${selectedRecord.id}/status`, body: { payment_status: item.value } },
                          {
                            onSuccess: async () => {
                              setNotice(`Статус платежа #${selectedRecord.id} обновлён.`);
                              pushToast({ title: "Статус обновлён", description: item.label, tone: item.value === "error" || item.value === "disputed" ? "warning" : "info" });
                              await queryClient.invalidateQueries({ queryKey: ["payments"] });
                            },
                          },
                        );
                      }}
                    >
                      {item.label}
                    </Button>
                  ))}
                  {selectedRecord.linked_user_context ? (
                    <>
                      <Button
                        type="button"
                        variant="ghost"
                        className="justify-start"
                        onClick={(event) => {
                          stopActionClick(event);
                          if (!confirmAction("Запустить синхронизацию доступа для пользователя этого платежа?")) {
                            return;
                          }
                          mutation.mutate(
                            { path: `/users/${selectedRecord.linked_user_context?.user_id}/sync` },
                            {
                              onSuccess: async (payload) => {
                                const feedback = describeRepairResult(payload as UserVpnRepairActionResult);
                                setNotice(feedback.description);
                                pushToast({ title: feedback.title, description: feedback.description, tone: feedback.tone });
                                await queryClient.invalidateQueries({ queryKey: ["payments"] });
                              },
                            },
                          );
                        }}
                        disabled={!selectedRecord.linked_user_context.repair_action?.can_repair}
                      >
                        Синхронизировать
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        className="justify-start"
                        onClick={(event) => {
                          stopActionClick(event);
                          if (!confirmAction("Запустить глубокий ремонт доступа для пользователя этого платежа?")) {
                            return;
                          }
                          mutation.mutate(
                            { path: `/users/${selectedRecord.linked_user_context?.user_id}/deep-repair` },
                            {
                              onSuccess: async (payload) => {
                                const feedback = describeRepairResult(payload as UserVpnRepairActionResult);
                                setNotice(feedback.description);
                                pushToast({
                                  title: (payload as UserVpnRepairActionResult).sync_failed ? "Ремонт с ошибками" : "Ремонт выполнен",
                                  description: feedback.description,
                                  tone: (payload as UserVpnRepairActionResult).sync_failed ? "warning" : "success",
                                });
                                await queryClient.invalidateQueries({ queryKey: ["payments"] });
                              },
                            },
                          );
                        }}
                        disabled={!permissions.can_run_deep_repair || !selectedRecord.linked_user_context.deep_repair_action?.can_deep_repair}
                      >
                        Глубокий ремонт
                      </Button>
                    </>
                  ) : null}
                </div>
              </Card>
            </div>
          </div>
        </DetailPanel>
      ) : null}
    </div>
  );
}
