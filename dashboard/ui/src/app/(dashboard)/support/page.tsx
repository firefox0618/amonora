"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, Card, EmptyState, Input, NoticeBanner, SectionHeading, Select, StatusBadge, Textarea } from "@/components/ui";
import { PageError, PageLoader } from "@/components/query-state";
import { useSession, useSupport } from "@/hooks/use-dashboard";
import { BASE_PATH } from "@/lib/api";
import { apiPost } from "@/lib/api";
import { describeRepairResult } from "@/lib/repair-feedback";
import { SupportPayload, UserVpnRepairActionResult } from "@/lib/types";
import { useToasts } from "@/components/toast-center";

const SUPPORT_STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  in_progress: "В работе",
  closed: "Закрыт",
};

function isImageAttachment(kind?: string | null, mimeType?: string | null) {
  return kind === "photo" || String(mimeType || "").startsWith("image/");
}

function isVideoAttachment(kind?: string | null, mimeType?: string | null) {
  return kind === "video" || kind === "video_note" || String(mimeType || "").startsWith("video/");
}

function isAudioAttachment(kind?: string | null, mimeType?: string | null) {
  return kind === "voice" || kind === "audio" || String(mimeType || "").startsWith("audio/");
}

function renderSupportAttachment(
  attachment: Record<string, unknown> | null,
  tone: "user" | "admin",
) {
  if (!attachment) return null;
  const rawAttachmentUrl = typeof attachment.url === "string" ? attachment.url : null;
  const attachmentKind = typeof attachment.kind === "string" ? attachment.kind : null;
  const mimeType = typeof attachment.mime_type === "string" ? attachment.mime_type : null;
  const attachmentName = typeof attachment.name === "string" ? attachment.name : "Вложение";
  const attachmentUrl = rawAttachmentUrl
    ? rawAttachmentUrl.startsWith("/dashboard/")
      ? `${BASE_PATH}/api/proxy${rawAttachmentUrl}`
      : rawAttachmentUrl
    : null;
  if (!attachmentUrl) return null;

  const commonClass =
    tone === "admin"
      ? "mt-3 rounded-[10px] border border-white/12 bg-white/8 p-2"
      : "mt-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] p-2";

  if (isImageAttachment(attachmentKind, mimeType)) {
    return (
      <div className={commonClass}>
        <a href={attachmentUrl} target="_blank" rel="noreferrer" className="block">
          <img src={attachmentUrl} alt={attachmentName} className="max-h-[280px] w-full rounded-[8px] object-contain" />
        </a>
        <a href={attachmentUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center text-[11px] font-medium underline-offset-2 hover:underline">
          Открыть фото
        </a>
      </div>
    );
  }

  if (isVideoAttachment(attachmentKind, mimeType)) {
    return (
      <div className={commonClass}>
        <video controls playsInline preload="metadata" className="max-h-[280px] w-full rounded-[8px]" src={attachmentUrl}>
          <track kind="captions" />
        </video>
        <a href={attachmentUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center text-[11px] font-medium underline-offset-2 hover:underline">
          Открыть видео
        </a>
      </div>
    );
  }

  if (isAudioAttachment(attachmentKind, mimeType)) {
    return (
      <div className={commonClass}>
        <audio controls preload="metadata" className="w-full" src={attachmentUrl}>
          <track kind="captions" />
        </audio>
        <a href={attachmentUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center text-[11px] font-medium underline-offset-2 hover:underline">
          Открыть аудио
        </a>
      </div>
    );
  }

  return (
    <a
      href={attachmentUrl}
      target="_blank"
      rel="noreferrer"
      className={`mt-3 inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium transition ${
        tone === "admin"
          ? "bg-white/15 text-white hover:bg-white/25"
          : "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
      }`}
    >
      Открыть: {attachmentName}
    </a>
  );
}

export default function SupportPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { pushToast } = useToasts();
  const session = useSession();
  const [filterMode, setFilterMode] = useState(searchParams.get("filter_mode") || "queue");
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [selectedTicketId, setSelectedTicketId] = useState<number | undefined>(
    searchParams.get("ticket_id") ? Number(searchParams.get("ticket_id")) : undefined,
  );
  const [reply, setReply] = useState("");
  const [targetAdminId, setTargetAdminId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    setFilterMode(searchParams.get("filter_mode") || "queue");
    setSearch(searchParams.get("q") || "");
    setSelectedTicketId(searchParams.get("ticket_id") ? Number(searchParams.get("ticket_id")) : undefined);
  }, [searchParams]);

  const supportQuery = useSupport(filterMode, deferredSearch, selectedTicketId);
  const permissions = session.data?.admin.permissions ?? {};
  const selectedTicket = supportQuery.data?.selected_ticket as SupportPayload["selected_ticket"];
  const linkedUserContext = selectedTicket?.linked_user_context ?? null;
  const isClosed = String(selectedTicket?.ticket?.status || "") === "closed";

  const mutation = useMutation({
    mutationFn: (payload: { path: string; body?: unknown }) => apiPost(payload.path, payload.body),
    onSuccess: async () => {
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["support"] });
      await queryClient.invalidateQueries({ queryKey: ["overview"] });
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (mutationError: Error) => {
      setError(mutationError.message);
      pushToast({ title: "Действие не выполнено", description: mutationError.message, tone: "error" });
    },
  });

  const counts = supportQuery.data?.counts ?? {};
  const tickets = supportQuery.data?.tickets ?? [];
  const adminChoices = supportQuery.data?.admin_choices ?? [];
  const effectiveTicketId = selectedTicket?.ticket?.user_id ? Number(selectedTicket.ticket.user_id) : undefined;

  const paymentSummary = useMemo(() => {
    const payments = selectedTicket?.payments ?? [];
    return payments.slice(0, 5);
  }, [selectedTicket?.payments]);

  const refreshSupport = async () => {
    setNotice("");
    setError("");
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["support"] }),
      queryClient.invalidateQueries({ queryKey: ["overview"] }),
      queryClient.invalidateQueries({ queryKey: ["payments"] }),
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    ]);
    setNotice("Поддержка обновлена.");
  };

  const confirmAction = (message: string) => {
    if (typeof window === "undefined") return true;
    return window.confirm(message);
  };

  if (supportQuery.isLoading) return <PageLoader />;
  if (supportQuery.error || !supportQuery.data) {
    return <PageError message={supportQuery.error?.message || "Не удалось загрузить поддержку"} />;
  }

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Поддержка"
        description="Очередь, диалог и связанный контекст."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input
              id="support-search"
              name="supportSearch"
              value={search}
              onChange={(event) => {
                const value = event.target.value;
                setSearch(value);
                const params = new URLSearchParams(searchParams.toString());
                if (value.trim()) params.set("q", value);
                else params.delete("q");
                router.replace(`/support${params.toString() ? `?${params.toString()}` : ""}`);
              }}
              placeholder="Поиск по TG ID или сообщению"
              className="w-full md:w-52"
            />
            <Select
              id="support-filter-mode"
              name="supportFilterMode"
              value={filterMode}
              onChange={(event) => {
                const value = event.target.value;
                setFilterMode(value);
                const params = new URLSearchParams(searchParams.toString());
                params.set("filter_mode", value);
                router.replace(`/support?${params.toString()}`);
              }}
            >
              <option value="queue">Очередь</option>
              <option value="new">Открытые</option>
              <option value="in_progress">В работе</option>
              <option value="closed">Закрытые</option>
              <option value="mine">Мои</option>
            </Select>
            <Button type="button" variant="ghost" onClick={() => void refreshSupport()}>
              Обновить
            </Button>
          </div>
        }
      />

      {notice ? <NoticeBanner tone="success">{notice}</NoticeBanner> : null}
      {error ? <NoticeBanner tone="error">{error}</NoticeBanner> : null}

      <div className="grid gap-3 xl:grid-cols-5">
        <Card><div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Всего</div><div className="mt-2 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{counts.all || 0}</div></Card>
        <Card><div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Новые</div><div className="mt-2 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{counts.new || 0}</div></Card>
        <Card><div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">В работе</div><div className="mt-2 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{counts.in_progress || 0}</div></Card>
        <Card><div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">На мне</div><div className="mt-2 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{counts.mine || 0}</div></Card>
        <Card><div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Закрытые</div><div className="mt-2 text-[1.2rem] font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">{counts.closed || 0}</div></Card>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[300px_minmax(0,1fr)_320px]">
        <Card className="overflow-hidden p-0">
          <div className="border-b border-[color:var(--surface-border)] px-4 py-3">
            <div className="text-[12px] font-semibold text-slate-950 dark:text-slate-50">Очередь</div>
          </div>
          <div className="divide-y divide-[color:var(--surface-border)]">
            {tickets.length ? (
              tickets.map((ticket) => {
                const userId = Number(ticket.user_id || 0);
                return (
                  <button
                    key={userId}
                    type="button"
                    onClick={() => {
                      setSelectedTicketId(userId);
                      const params = new URLSearchParams(searchParams.toString());
                      params.set("ticket_id", String(userId));
                      router.replace(`/support?${params.toString()}`);
                    }}
                    className={`w-full px-4 py-3 text-left transition hover:bg-white/35 dark:hover:bg-white/4 ${
                      selectedTicketId === userId ? "bg-white/40 dark:bg-white/4" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-[12px] font-semibold text-slate-950 dark:text-slate-50">
                          {String(ticket.username || ticket.full_name || "—")}
                        </div>
                        <div className="truncate text-[11px] text-[color:var(--text-muted)]">
                          {String(ticket.last_user_message_preview || "—")}
                        </div>
                      </div>
                      <StatusBadge status={String(ticket.status)} label={SUPPORT_STATUS_LABELS[String(ticket.status)] || String(ticket.status)} />
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="px-4 py-8 text-[11px] text-[color:var(--text-muted)]">Очередь пуста.</div>
            )}
          </div>
        </Card>

        <Card className="overflow-hidden p-0">
          <div className="border-b border-[color:var(--surface-border)] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-[12px] font-semibold text-slate-950 dark:text-slate-50">
                  {selectedTicket ? String(selectedTicket.user?.username || selectedTicket.user?.telegram_id || "Диалог") : "Диалог"}
                </div>
                <div className="truncate text-[11px] text-[color:var(--text-muted)]">
                  {selectedTicket ? `Telegram ID ${selectedTicket.user?.telegram_id || "—"}` : "Выберите обращение слева"}
                </div>
              </div>
              {selectedTicket ? (
                <StatusBadge
                  status={String(selectedTicket.ticket.status)}
                  label={SUPPORT_STATUS_LABELS[String(selectedTicket.ticket.status)] || String(selectedTicket.ticket.status)}
                />
              ) : null}
            </div>
          </div>

          {selectedTicket ? (
            <div className="space-y-3 p-3">
              <div className="min-h-[64vh] max-h-[64vh] space-y-3 overflow-auto rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] p-3">
                {selectedTicket.history.length ? (
                  selectedTicket.history.map((message, index) => {
                    const role = String(message.role || "user");
                    const attachment =
                      typeof message.attachment === "object" && message.attachment !== null
                        ? (message.attachment as Record<string, unknown>)
                        : null;
                    return (
                      <div
                        key={`${message.timestamp}-${index}`}
                        className={`max-w-[88%] rounded-[12px] px-3 py-2 text-[12px] leading-5 ${
                          role === "admin"
                            ? "ml-auto bg-slate-950 text-white dark:bg-[#243447]"
                            : "bg-white text-slate-700 dark:bg-slate-950 dark:text-slate-200"
                        }`}
                      >
                        <div className="mb-1 text-[10px] opacity-70">{String(message.sender_name || role)}</div>
                        <div className="break-words whitespace-pre-wrap">{String(message.text || "—")}</div>
                        {renderSupportAttachment(attachment, role === "admin" ? "admin" : "user")}
                      </div>
                    );
                  })
                ) : (
                  <div className="rounded-[10px] border border-dashed border-[color:var(--surface-border)] px-4 py-6 text-[11px] text-[color:var(--text-muted)]">
                    У этого обращения пока нет истории.
                  </div>
                )}
              </div>

              <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
                <Textarea
                  id="support-reply"
                  name="supportReply"
                  value={reply}
                  onChange={(event) => setReply(event.target.value)}
                  placeholder="Ответ пользователю..."
                  className="lg:min-h-[92px]"
                />
                <Button
                  className="w-full"
                  onClick={() => {
                    if (!confirmAction("Отправить этот ответ пользователю?")) {
                      return;
                    }
                    mutation.mutate(
                      { path: `/support/${effectiveTicketId}/reply`, body: { message: reply } },
                      {
                        onSuccess: () => {
                          setNotice("Ответ отправлен пользователю.");
                          pushToast({ title: "Ответ отправлен", description: "Пользователь получил сообщение.", tone: "success" });
                          setReply("");
                        },
                      },
                    );
                  }}
                  disabled={mutation.isPending || !reply.trim()}
                >
                  Ответить
                </Button>
                <Button
                  variant="ghost"
                  className="w-full"
                  onClick={() => {
                    if (!confirmAction("Закрепить этот диалог за собой?")) {
                      return;
                    }
                    mutation.mutate(
                      { path: `/support/${effectiveTicketId}/assign` },
                      {
                        onSuccess: () => {
                          setNotice("Диалог закреплён за тобой.");
                          pushToast({ title: "Диалог взят", description: "Ответственный обновлён.", tone: "info" });
                        },
                      },
                    );
                  }}
                  disabled={mutation.isPending || isClosed}
                >
                  Взять
                </Button>
                <Button
                  variant="danger"
                  className="w-full"
                  onClick={() => {
                    if (!confirmAction("Закрыть обращение? При новом сообщении пользователя диалог откроется снова.")) {
                      return;
                    }
                    mutation.mutate(
                      { path: `/support/${effectiveTicketId}/close` },
                      {
                        onSuccess: (payload) => {
                          const userNotified =
                            payload &&
                            typeof payload === "object" &&
                            "close_result" in (payload as Record<string, unknown>) &&
                            Boolean((payload as { close_result?: { user_notified?: boolean } }).close_result?.user_notified);
                          setNotice(
                            userNotified
                              ? "Обращение закрыто, пользователь уведомлён."
                              : "Обращение закрыто. При новом сообщении диалог снова откроется.",
                          );
                          pushToast({ title: "Диалог закрыт", description: "Статус обращения обновлён.", tone: "success" });
                          setSelectedTicketId(undefined);
                          const params = new URLSearchParams(searchParams.toString());
                          params.delete("ticket_id");
                          router.replace(`/support${params.toString() ? `?${params.toString()}` : ""}`);
                        },
                      },
                    );
                  }}
                  disabled={mutation.isPending || isClosed}
                >
                  Закрыть
                </Button>
              </div>

              {reply.trim() ? (
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
                  Печатается ответ
                </div>
              ) : null}
            </div>
          ) : (
            <div className="p-4">
              <EmptyState title="Выбери обращение" description="Открой диалог слева, чтобы увидеть историю и ответить пользователю." />
            </div>
          )}
        </Card>

        <Card className="overflow-hidden p-0">
          <div className="border-b border-[color:var(--surface-border)] px-4 py-3">
            <div className="text-[12px] font-semibold text-slate-950 dark:text-slate-50">Связанный контекст</div>
          </div>
          {selectedTicket ? (
            <div className="space-y-3 p-3">
              {linkedUserContext ? (
                <>
                  <Card className="space-y-2 p-3">
                    <div className="grid gap-2 text-[11px]">
                      <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">Пользователь</span><span className="font-semibold text-slate-950 dark:text-slate-50">{linkedUserContext.username}</span></div>
                      <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">Тариф</span><span className="font-semibold text-slate-950 dark:text-slate-50">{linkedUserContext.plan_label}</span></div>
                      <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">Доступ</span><StatusBadge status={linkedUserContext.status_state} label={linkedUserContext.status_label || linkedUserContext.access_status} /></div>
                      <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">До</span><span className="font-semibold text-slate-950 dark:text-slate-50">{linkedUserContext.access_expires_at}</span></div>
                      <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--text-muted)]">Устройства</span><span className="font-semibold text-slate-950 dark:text-slate-50">{linkedUserContext.devices_count}</span></div>
                    </div>
                  </Card>

                  <div className="grid gap-2">
                    <Link href={linkedUserContext.user_href} className="inline-flex items-center rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[11px] font-medium text-slate-700 transition hover:border-[color:var(--accent)] hover:text-slate-950 dark:bg-[var(--surface-muted)] dark:text-slate-200 dark:hover:text-white">
                      Открыть пользователя
                    </Link>
                    {linkedUserContext.latest_payment_href ? (
                      <Link href={linkedUserContext.latest_payment_href} className="inline-flex items-center rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[11px] font-medium text-slate-700 transition hover:border-[color:var(--accent)] hover:text-slate-950 dark:bg-[var(--surface-muted)] dark:text-slate-200 dark:hover:text-white">
                        Открыть платёж
                      </Link>
                    ) : null}
                    <Button
                      variant="ghost"
                      className="justify-start"
                      onClick={() => {
                        if (!confirmAction("Запустить синхронизацию доступа для этого пользователя из обращения?")) {
                          return;
                        }
                        mutation.mutate(
                          { path: `/users/${linkedUserContext.user_id}/sync` },
                          {
                            onSuccess: async (payload) => {
                              const feedback = describeRepairResult(payload as UserVpnRepairActionResult);
                              setNotice(feedback.description);
                              pushToast({ title: feedback.title, description: feedback.description, tone: feedback.tone });
                              await Promise.all([
                                queryClient.invalidateQueries({ queryKey: ["users"] }),
                                queryClient.invalidateQueries({ queryKey: ["user-detail", linkedUserContext.user_id] }),
                                queryClient.invalidateQueries({ queryKey: ["payments"] }),
                              ]);
                            },
                          },
                        );
                      }}
                      disabled={!linkedUserContext.sync_action?.can_sync}
                    >
                      Синхронизировать
                    </Button>
                    <Button
                      variant="secondary"
                      className="justify-start"
                      onClick={() => {
                        if (!confirmAction("Запустить глубокий ремонт доступа для этого пользователя из обращения?")) {
                          return;
                        }
                        mutation.mutate(
                          { path: `/users/${linkedUserContext.user_id}/deep-repair` },
                          {
                            onSuccess: async (payload) => {
                              const feedback = describeRepairResult(payload as UserVpnRepairActionResult);
                              setNotice(feedback.description);
                              pushToast({
                                title: (payload as UserVpnRepairActionResult).sync_failed ? "Ремонт с ошибками" : "Ремонт выполнен",
                                description: feedback.description,
                                tone: (payload as UserVpnRepairActionResult).sync_failed ? "warning" : "success",
                              });
                              await Promise.all([
                                queryClient.invalidateQueries({ queryKey: ["users"] }),
                                queryClient.invalidateQueries({ queryKey: ["user-detail", linkedUserContext.user_id] }),
                                queryClient.invalidateQueries({ queryKey: ["payments"] }),
                              ]);
                            },
                          },
                        );
                      }}
                      disabled={!permissions.can_run_deep_repair || !linkedUserContext.deep_repair_action?.can_deep_repair}
                    >
                      Глубокий ремонт
                    </Button>
                  </div>
                </>
              ) : null}

              <Card className="space-y-2 p-3">
                <div className="text-[12px] font-semibold text-slate-950 dark:text-slate-50">Передача</div>
                <Select id="support-transfer-admin" name="supportTransferAdminId" value={targetAdminId} onChange={(event) => setTargetAdminId(event.target.value)}>
                  <option value="">Кому передать</option>
                  {adminChoices.map((item) => (
                    <option key={String(item.telegram_id)} value={String(item.telegram_id)}>
                      {String(item.display_name)}
                    </option>
                  ))}
                </Select>
                <Button
                  variant="ghost"
                  className="justify-start"
                  onClick={() => {
                    if (!confirmAction("Передать это обращение другому администратору?")) {
                      return;
                    }
                    mutation.mutate(
                      { path: `/support/${effectiveTicketId}/transfer`, body: { target_admin_id: Number(targetAdminId) } },
                      {
                        onSuccess: () => {
                          setNotice("Тикет передан.");
                          pushToast({ title: "Тикет передан", description: "Ответственный обновлён.", tone: "info" });
                        },
                      },
                    );
                  }}
                  disabled={!targetAdminId || !effectiveTicketId}
                >
                  Передать
                </Button>
              </Card>

              <Card className="space-y-2 p-3">
                <div className="text-[12px] font-semibold text-slate-950 dark:text-slate-50">Платежи</div>
                {paymentSummary.length ? (
                  paymentSummary.map((payment) => (
                    <div key={payment.id} className="flex items-center justify-between gap-2 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-3 py-2 text-[11px]">
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-slate-950 dark:text-slate-50">#{payment.id}</div>
                        <div className="truncate text-[color:var(--text-muted)]">{payment.created_at}</div>
                      </div>
                      <StatusBadge status={payment.payment_status} label={payment.payment_status_label} />
                    </div>
                  ))
                ) : (
                  <div className="text-[11px] text-[color:var(--text-muted)]">Платежей пока нет.</div>
                )}
              </Card>
            </div>
          ) : (
            <div className="p-4">
              <EmptyState title="Нет контекста" description="После выбора диалога здесь появится пользователь и его платежи." />
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
