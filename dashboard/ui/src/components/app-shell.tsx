"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Bell,
  BarChart3,
  BookOpen,
  Camera,
  LayoutDashboard,
  LifeBuoy,
  Loader2,
  LogOut,
  Menu,
  MoonStar,
  ScrollText,
  Settings2,
  Shield,
  SunMedium,
  Users,
  WalletCards,
  Waves,
  X,
} from "lucide-react";
import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiPost, apiUpload } from "@/lib/api";
import { Button, Card, NoticeBanner } from "@/components/ui";
import { useTheme } from "@/components/theme-provider";
import { useToasts } from "@/components/toast-center";
import { useNotifications } from "@/hooks/use-dashboard";
import { SessionPayload } from "@/lib/types";
import { cn } from "@/lib/utils";

const icons = {
  overview: LayoutDashboard,
  users: Users,
  servers: Shield,
  traffic: Waves,
  payments: WalletCards,
  analytics: BarChart3,
  support: LifeBuoy,
  knowledge: BookOpen,
  audit: ScrollText,
  settings: Settings2,
};

const EKB_TIMEZONE = "Asia/Yekaterinburg";
const ekbDateFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: EKB_TIMEZONE,
  day: "2-digit",
  month: "long",
  year: "numeric",
});
const ekbTimeFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: EKB_TIMEZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function notificationSignature(item: { kind?: string; title?: string; text?: string; href?: string; meta?: string }) {
  return [item.kind || "", item.title || "", item.text || "", item.href || "", item.meta || ""].join("|");
}

export function AppShell({
  session,
  children,
}: {
  session: SessionPayload;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { theme, toggleTheme } = useTheme();
  const { pushToast } = useToasts();
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [ekbNow, setEkbNow] = useState(() => Date.now());
  const [readNotificationIds, setReadNotificationIds] = useState<string[]>([]);
  const [dismissedNotificationIds, setDismissedNotificationIds] = useState<string[]>([]);
  const [dismissedNotificationKeys, setDismissedNotificationKeys] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const notificationsWrapperRef = useRef<HTMLDivElement | null>(null);
  const logoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seenNotificationIdsRef = useRef<string[]>([]);

  const admin = session.admin ?? {
    id: 0,
    username: "admin",
    display_name: "Администратор",
    initials: "A",
    role: "unknown",
    role_name: "Неизвестно",
    telegram_id: null,
    avatar_url: null,
    last_login_at: null,
    permissions: {},
  };
  const profile = session.profile ?? {
    telegram_id: null,
    avatar_url: null,
    last_login_at: null,
    session_idle_minutes: 30,
    session_hours: 12,
  };
  const navigation = Array.isArray(session.navigation) ? session.navigation : [];
  const nav = useMemo(
    () =>
      navigation.map((item) => ({
        ...item,
        icon: icons[item.key as keyof typeof icons] || LayoutDashboard,
      })),
    [navigation],
  );
  const notificationStorageKey = useMemo(() => `amonora-dashboard-notifications:${admin.id || "anon"}`, [admin.id]);
  const activeItem = nav.find((item) => pathname === item.href) ?? nav[0] ?? { key: "overview", label: "Панель управления", href: "/overview", icon: LayoutDashboard };
  const initials = admin.initials || admin.display_name.slice(0, 1).toUpperCase() || "A";
  const notificationsQuery = useNotifications(true);
  const notificationItems = notificationsQuery.data?.items ?? [];
  const visibleNotificationItems = useMemo(
    () =>
      notificationItems.filter(
        (item) =>
          !dismissedNotificationIds.includes(item.id) &&
          !dismissedNotificationKeys.includes(notificationSignature(item)),
      ),
    [dismissedNotificationIds, dismissedNotificationKeys, notificationItems],
  );
  const unreadNotificationCount = useMemo(
    () => visibleNotificationItems.filter((item) => !readNotificationIds.includes(item.id)).length,
    [visibleNotificationItems, readNotificationIds],
  );

  const runLogout = useCallback(async (notice?: string) => {
    try {
      await apiPost("/auth/logout");
    } catch {
      // Transport errors should not leave the operator in a broken auth state.
    } finally {
      const suffix = notice ? `?notice=${encodeURIComponent(notice)}` : "";
      router.replace(`/login${suffix}`);
    }
  }, [router]);

  useEffect(() => {
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!notificationsWrapperRef.current?.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setSidebarOpen(false);
        setProfileOpen(false);
        setNotificationsOpen(false);
      }
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
    setNotificationsOpen(false);
  }, [pathname]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setEkbNow(Date.now());
    }, 15_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!notificationsQuery.data?.items?.length) {
      return;
    }
    const currentIds = notificationsQuery.data.items.map((item) => item.id);
    if (!seenNotificationIdsRef.current.length) {
      seenNotificationIdsRef.current = currentIds;
      return;
    }
    const freshItems = notificationsQuery.data.items.filter((item) => !seenNotificationIdsRef.current.includes(item.id));
    if (freshItems.length) {
      freshItems.slice(0, 3).forEach((item) => {
        pushToast({
          title: item.title,
          description: item.text,
          tone: item.kind === "payment" ? "success" : "info",
        });
      });
    }
    seenNotificationIdsRef.current = currentIds;
  }, [notificationsQuery.data?.items, pushToast]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(notificationStorageKey);
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw) as { read?: string[]; dismissed?: string[]; dismissedKeys?: string[] } | null;
      setReadNotificationIds(Array.isArray(parsed?.read) ? parsed.read.filter((item) => typeof item === "string") : []);
      setDismissedNotificationIds(Array.isArray(parsed?.dismissed) ? parsed.dismissed.filter((item) => typeof item === "string") : []);
      setDismissedNotificationKeys(Array.isArray(parsed?.dismissedKeys) ? parsed.dismissedKeys.filter((item) => typeof item === "string") : []);
    } catch {
      // Ignore stale storage payloads.
    }
  }, [notificationStorageKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        notificationStorageKey,
        JSON.stringify({
          read: readNotificationIds,
          dismissed: dismissedNotificationIds,
          dismissedKeys: dismissedNotificationKeys,
        }),
      );
    } catch {
      // Ignore local storage write errors.
    }
  }, [dismissedNotificationIds, dismissedNotificationKeys, notificationStorageKey, readNotificationIds]);

  useEffect(() => {
    const currentIds = notificationItems.map((item) => item.id);
    setReadNotificationIds((previous) => previous.filter((id) => currentIds.includes(id)));
    setDismissedNotificationIds((previous) => previous.filter((id) => currentIds.includes(id)));
  }, [notificationItems]);

  useEffect(() => {
    if (!notificationsOpen || !visibleNotificationItems.length) {
      return;
    }
    setReadNotificationIds(visibleNotificationItems.map((item) => item.id));
  }, [visibleNotificationItems, notificationsOpen]);

  useEffect(() => {
    const resetTimer = () => {
      if (logoutTimerRef.current) {
        clearTimeout(logoutTimerRef.current);
      }
      logoutTimerRef.current = setTimeout(() => {
        void runLogout("Сессия завершена из-за бездействия.");
      }, profile.session_idle_minutes * 60 * 1000);
    };

    const events = ["mousemove", "keydown", "click", "scroll", "touchstart"];
    events.forEach((eventName) => window.addEventListener(eventName, resetTimer, { passive: true }));
    resetTimer();

    return () => {
      if (logoutTimerRef.current) {
        clearTimeout(logoutTimerRef.current);
      }
      events.forEach((eventName) => window.removeEventListener(eventName, resetTimer));
    };
  }, [profile.session_idle_minutes, runLogout]);

  const avatarMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("avatar", file);
      return apiUpload<{ session: SessionPayload }>("/profile/avatar", formData);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });

  const onAvatarChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    avatarMutation.mutate(file);
    event.target.value = "";
  };

  const ekbTimeLabel = ekbTimeFormatter.format(ekbNow);
  const ekbDateLabel = ekbDateFormatter.format(ekbNow);
  const clearUnreadNotifications = useCallback(() => {
    setReadNotificationIds(visibleNotificationItems.map((item) => item.id));
  }, [visibleNotificationItems]);

  const clearNotificationPanel = useCallback(() => {
    setReadNotificationIds(visibleNotificationItems.map((item) => item.id));
    setDismissedNotificationIds((current) => Array.from(new Set([...current, ...visibleNotificationItems.map((item) => item.id)])));
    setDismissedNotificationKeys((current) =>
      Array.from(new Set([...current, ...visibleNotificationItems.map((item) => notificationSignature(item))])).slice(-200),
    );
  }, [visibleNotificationItems]);

  const sidebar = (
    <Card className="relative h-full overflow-hidden p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] bg-[linear-gradient(135deg,#5d6973,#909ba4)] text-sm font-semibold text-white shadow-[0_18px_28px_-24px_rgba(15,23,32,0.4)]">
            A
          </div>
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50">Amonora Control</div>
          </div>
        </div>
        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-[12px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] lg:hidden"
          onClick={() => setSidebarOpen(false)}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mb-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[rgba(255,255,255,0.18)] px-3 py-2 text-[11px] text-[color:var(--text-muted)] dark:bg-[rgba(255,255,255,0.02)]">
        <div className="font-semibold text-slate-900 dark:text-slate-100">{admin.role_name}</div>
      </div>

      <nav className="space-y-0.5">
        {nav.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.key}
              href={item.href}
              className={cn(
                "group flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 transition",
                isActive
                  ? "bg-[rgba(93,131,152,0.12)] text-slate-950 dark:bg-[rgba(156,182,196,0.12)] dark:text-slate-50"
                  : "text-slate-700 hover:bg-[rgba(93,131,152,0.06)] hover:text-slate-950 dark:text-slate-200 dark:hover:bg-[rgba(156,182,196,0.08)] dark:hover:text-white",
              )}
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-[8px]",
                  isActive
                    ? "bg-[rgba(255,255,255,0.56)] dark:bg-[rgba(255,255,255,0.08)]"
                    : "bg-transparent",
                )}>
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-[12px] font-medium">{item.label}</div>
                </div>
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="mt-3 rounded-[10px] border border-[color:var(--surface-border)] bg-[rgba(255,255,255,0.18)] px-3 py-2 dark:bg-[rgba(255,255,255,0.02)]">
        <div className="flex items-center justify-between gap-3 text-[11px] text-[color:var(--text-muted)]">
          <span>Idle {profile.session_idle_minutes} min</span>
          <span>2FA Telegram</span>
        </div>
      </div>
    </Card>
  );

  return (
    <div className="min-h-screen text-slate-900 dark:text-slate-100">
      <div className="mx-auto max-w-[1580px] px-3 py-2.5 md:px-4 md:py-3">
        <div className="grid gap-3 lg:grid-cols-[250px_minmax(0,1fr)] xl:grid-cols-[268px_minmax(0,1fr)]">
          <aside className="hidden lg:block">{sidebar}</aside>

          <div className="space-y-1.5">
            <header className="sticky top-0 z-40">
              <Card className="overflow-visible px-3 py-1.5">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setSidebarOpen(true)}
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] lg:hidden"
                    >
                      <Menu className="h-4 w-4" />
                    </button>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h1 className="text-[1rem] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50 md:text-[1.1rem]">{activeItem.label}</h1>
                        <span className="rounded-full border border-[color:var(--surface-border)] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
                          {admin.role_name}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="hidden min-w-0 flex-1 flex-col items-center justify-center text-center md:flex">
                    <div className="text-[14px] font-semibold tracking-[-0.04em] text-slate-950 dark:text-slate-50 lg:text-[16px]">
                      {ekbTimeLabel} · {ekbDateLabel}
                    </div>
                    <div
                      className={cn(
                        "mt-0.5 text-[11px] font-medium",
                        unreadNotificationCount
                          ? "text-[#8a5209] dark:text-[#ffd7a0]"
                          : "text-emerald-700 dark:text-emerald-300",
                      )}
                    >
                      {unreadNotificationCount ? `${unreadNotificationCount} новых` : "Система в норме"}
                    </div>
                  </div>

                  <div className="flex min-w-0 flex-1 shrink-0 flex-wrap items-center justify-end gap-2">
                    <button
                      className="flex h-8 w-8 items-center justify-center rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] text-slate-600 dark:bg-[var(--surface-muted)] dark:text-slate-200"
                      onClick={toggleTheme}
                      title={theme === "dark" ? "Переключить на светлую тему" : "Переключить на тёмную тему"}
                      type="button"
                    >
                      {theme === "dark" ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
                    </button>

                    <div ref={notificationsWrapperRef} className="relative">
                      <button
                        className={cn(
                          "relative flex h-8 w-8 items-center justify-center rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] text-slate-600 dark:bg-[var(--surface-muted)] dark:text-slate-200",
                          notificationsOpen && "border-[color:var(--accent)] text-slate-950 dark:text-white",
                        )}
                        onClick={() =>
                          setNotificationsOpen((value) => {
                            const next = !value;
                            if (next) {
                              clearUnreadNotifications();
                            }
                            return next;
                          })
                        }
                        type="button"
                      >
                        <Bell className="h-4 w-4" />
                        {unreadNotificationCount ? (
                          <span className="absolute -right-1 -top-1 flex min-w-[22px] items-center justify-center rounded-full bg-rose-500 px-1.5 py-0.5 text-[11px] font-semibold text-white shadow-lg shadow-rose-400/30">
                            {unreadNotificationCount > 99 ? "99+" : unreadNotificationCount}
                          </span>
                        ) : null}
                      </button>

                      {notificationsOpen ? (
                        <div className="absolute right-0 top-[calc(100%+12px)] z-40 w-[min(92vw,420px)]">
                          <Card className="space-y-4 p-4">
                            <div className="flex items-center justify-between gap-3">
                              <div className="text-xl font-semibold tracking-[-0.05em] text-slate-950 dark:text-slate-50">Уведомления</div>
                              <span className="rounded-full bg-[rgba(255,180,91,0.16)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8a5209] dark:text-[#ffd7a0]">
                                {unreadNotificationCount}
                              </span>
                            </div>

                            {notificationsQuery.isLoading ? (
                              <NoticeBanner>Обновляю сигналы панели...</NoticeBanner>
                            ) : visibleNotificationItems.length ? (
                              <div className="max-h-[68vh] space-y-2 overflow-auto pr-1">
                                <div className="flex items-center justify-end">
                                  <Button type="button" variant="ghost" className="h-7 px-2.5 py-1 text-[10px]" onClick={clearNotificationPanel}>
                                    Очистить
                                  </Button>
                                </div>
                                {visibleNotificationItems.map((item) => (
                                  <Link
                                    key={item.id}
                                    href={item.href}
                                    onClick={() => {
                                      clearUnreadNotifications();
                                      setNotificationsOpen(false);
                                    }}
                                    className="block rounded-[22px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-4 py-3 transition hover:border-[color:var(--accent)] dark:bg-[var(--surface-muted)]"
                                  >
                                    <div className="flex items-start justify-between gap-3">
                                      <div className="min-w-0">
                                        <div className="truncate font-semibold text-slate-950 dark:text-slate-50">{item.title}</div>
                                        <div className="mt-1 break-words text-sm text-[color:var(--text-muted)]">{item.text}</div>
                                      </div>
                                      {item.meta ? (
                                        <span className="rounded-full border border-[color:var(--surface-border)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[color:var(--text-muted)]">
                                          {item.meta}
                                        </span>
                                      ) : null}
                                    </div>
                                  </Link>
                                ))}
                              </div>
                            ) : (
                              <NoticeBanner tone="info">Новых уведомлений пока нет.</NoticeBanner>
                            )}
                          </Card>
                        </div>
                      ) : null}
                    </div>

                    <button
                      className="flex min-w-0 items-center gap-2.5 rounded-[10px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-2.5 py-1.5 dark:bg-[var(--surface-muted)]"
                      onClick={() => setProfileOpen((value) => !value)}
                      type="button"
                    >
                      {admin.avatar_url ? (
                        <Image
                          src={admin.avatar_url}
                          alt={admin.display_name}
                          width={44}
                          height={44}
                          unoptimized
                          className="h-8 w-8 rounded-[10px] object-cover ring-1 ring-[color:var(--surface-border)]"
                        />
                      ) : (
                        <div className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-[linear-gradient(135deg,#607b89,#96a5ae)] text-xs font-semibold text-white">
                          {initials}
                        </div>
                      )}
                      <div className="hidden min-w-0 text-left sm:block">
                        <div className="truncate text-[12px] font-semibold text-slate-950 dark:text-slate-50">{admin.display_name}</div>
                        <p className="truncate text-[10px] text-[color:var(--text-muted)]">@{admin.username}</p>
                      </div>
                    </button>

                    <Button variant="ghost" onClick={() => void runLogout()} type="button" className="hidden sm:inline-flex">
                      Выйти
                    </Button>
                  </div>
                </div>
              </Card>
            </header>

            <main className="page-enter">{children}</main>
          </div>
        </div>
      </div>

      {sidebarOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-slate-950/55 backdrop-blur-sm" onClick={() => setSidebarOpen(false)} />
          <div className="absolute inset-3 overflow-hidden">{sidebar}</div>
        </div>
      ) : null}

      {profileOpen ? (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-slate-950/45 backdrop-blur-sm" onClick={() => setProfileOpen(false)} />
          <div className="absolute inset-y-3 right-3 w-[min(92vw,430px)]">
            <Card className="flex h-full flex-col space-y-5 overflow-auto p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[color:var(--accent)]">Operator profile</div>
                  <h3 className="mt-2 text-2xl font-semibold tracking-[-0.06em] text-slate-950 dark:text-slate-50">{admin.display_name}</h3>
                  <p className="mt-1 text-sm text-[color:var(--text-muted)]">@{admin.username}</p>
                </div>
                <button
                  className="flex h-11 w-11 items-center justify-center rounded-[18px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] dark:bg-[var(--surface-muted)]"
                  onClick={() => setProfileOpen(false)}
                  type="button"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="rounded-[28px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] p-4 dark:bg-[var(--surface-muted)]">
                <div className="flex items-center gap-4">
                  {admin.avatar_url ? (
                    <Image
                      src={admin.avatar_url}
                      alt={admin.display_name}
                      width={88}
                      height={88}
                      unoptimized
                      className="h-[5.5rem] w-[5.5rem] rounded-[24px] object-cover ring-1 ring-[color:var(--surface-border)]"
                    />
                  ) : (
                    <div className="flex h-[5.5rem] w-[5.5rem] items-center justify-center rounded-[24px] bg-[linear-gradient(135deg,#0f4c81,#1098ad)] text-2xl font-semibold text-white">
                      {initials}
                    </div>
                  )}
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="text-sm text-[color:var(--text-muted)]">
                      Последний вход: <span className="font-medium text-slate-800 dark:text-slate-100">{profile.last_login_at || "—"}</span>
                    </div>
                    <div className="text-sm text-[color:var(--text-muted)]">
                      Idle timeout: <span className="font-medium text-slate-800 dark:text-slate-100">{profile.session_idle_minutes} мин</span>
                    </div>
                    <div className="text-sm text-[color:var(--text-muted)]">
                      Полная сессия: <span className="font-medium text-slate-800 dark:text-slate-100">{profile.session_hours} ч</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-[22px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-4 py-3 dark:bg-[var(--surface-muted)]">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Role</div>
                  <div className="mt-2 font-semibold text-slate-950 dark:text-slate-50">{admin.role_name}</div>
                </div>
                <div className="rounded-[22px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-4 py-3 dark:bg-[var(--surface-muted)]">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-muted)]">Telegram</div>
                  <div className="mt-2 font-semibold text-slate-950 dark:text-slate-50">{profile.telegram_id || "—"}</div>
                </div>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                id="profile-avatar-upload"
                name="profileAvatar"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={onAvatarChange}
              />

              <div className="grid gap-3 sm:grid-cols-2">
                <Button variant="ghost" onClick={() => fileInputRef.current?.click()} disabled={avatarMutation.isPending} type="button">
                  {avatarMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Camera className="mr-2 h-4 w-4" />}
                  Обновить аватар
                </Button>
                <Button variant="danger" onClick={() => void runLogout()} type="button">
                  <LogOut className="mr-2 h-4 w-4" />
                  Выйти
                </Button>
              </div>

              {avatarMutation.error ? <NoticeBanner tone="error">{avatarMutation.error.message}</NoticeBanner> : null}
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}
