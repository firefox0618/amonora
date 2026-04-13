"use client";

import { MoonStar, Shield, SunMedium } from "lucide-react";
import { useState } from "react";
import { useTheme } from "@/components/theme-provider";
import { Button, Card, Input } from "@/components/ui";

const LOGIN_USERNAME_KEY = "amonora-dashboard-login-username";

export default function LoginPage() {
  const { theme, toggleTheme } = useTheme();
  const [username, setUsername] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return new URLSearchParams(window.location.search).get("username") || "";
  });
  const [password, setPassword] = useState("");
  const [notice] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return new URLSearchParams(window.location.search).get("notice") || "";
  });
  const [error] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return new URLSearchParams(window.location.search).get("error") || "";
  });

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div className="absolute inset-0 control-grid opacity-50" />
      <div className="absolute right-5 top-5 z-10">
        <Button variant="ghost" onClick={toggleTheme} type="button">
          {theme === "dark" ? <SunMedium className="mr-2 h-4 w-4" /> : <MoonStar className="mr-2 h-4 w-4" />}
          {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
        </Button>
      </div>

      <Card className="grid w-full max-w-5xl gap-0 overflow-hidden p-0 lg:grid-cols-[1.02fr_0.98fr]">
        <div className="control-grid relative overflow-hidden bg-[linear-gradient(145deg,#d7dbe0,#c8ced5_54%,#b4bcc5_100%)] p-7 text-slate-900 dark:bg-[linear-gradient(145deg,#20242a,#2a3037_54%,#3d464f_100%)] dark:text-white lg:p-8">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.22),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(90,101,112,0.08),transparent_22%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.12),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(255,255,255,0.08),transparent_22%)]" />
          <div className="relative">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-[20px] bg-white/40 ring-1 ring-slate-700/8 dark:bg-white/12 dark:ring-white/12">
                <Shield className="h-6 w-6" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-[-0.05em]">Amonora Control</h1>
                <p className="text-[13px] text-slate-800/80 dark:text-white/72">Панель управления Amonora</p>
              </div>
            </div>

            <div className="mt-10 space-y-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-800/78 dark:text-white/74">ACCESS • PAYMENTS • SUPPORT</p>
                <h2 className="mt-3 max-w-xl text-3xl font-semibold tracking-[-0.06em]">
                  Быстрый вход в control center.
                </h2>
              </div>
              <p className="max-w-md text-[13px] leading-6 text-slate-800/84 dark:text-white/76">
                Сначала логин и пароль, затем код в Telegram. Только после этого открывается рабочая сессия.
              </p>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[22px] border border-slate-800/10 bg-white/52 p-3.5 shadow-[0_16px_28px_-24px_rgba(15,23,42,0.2)] dark:border-white/12 dark:bg-white/8 dark:shadow-none">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-700/68 dark:text-white/56">2FA</div>
                <div className="mt-1.5 text-xl font-semibold tracking-[-0.05em]">Telegram</div>
                <div className="mt-1.5 text-[13px] text-slate-700/82 dark:text-white/68">Код приходит администратору.</div>
              </div>
              <div className="rounded-[22px] border border-slate-800/10 bg-white/52 p-3.5 shadow-[0_16px_28px_-24px_rgba(15,23,42,0.2)] dark:border-white/12 dark:bg-white/8 dark:shadow-none">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-700/68 dark:text-white/56">Session</div>
                <div className="mt-1.5 text-xl font-semibold tracking-[-0.05em]">Protected</div>
                <div className="mt-1.5 text-[13px] text-slate-700/82 dark:text-white/68">Доступ только для whitelist.</div>
              </div>
              <div className="rounded-[22px] border border-slate-800/10 bg-white/52 p-3.5 shadow-[0_16px_28px_-24px_rgba(15,23,42,0.2)] dark:border-white/12 dark:bg-white/8 dark:shadow-none">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-700/68 dark:text-white/56">Timezone</div>
                <div className="mt-1.5 text-xl font-semibold tracking-[-0.05em]">EKB</div>
                <div className="mt-1.5 text-[13px] text-slate-700/82 dark:text-white/68">Единая операционная зона.</div>
              </div>
            </div>
          </div>
        </div>

        <div className="p-6 lg:p-8">
          <div className="mx-auto max-w-md">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-[rgba(16,152,173,0.12)] text-[color:var(--accent)]">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[color:var(--accent)]">Auth bridge</p>
              <h2 className="text-2xl font-semibold tracking-[-0.06em] text-slate-950 dark:text-slate-50">Вход</h2>
            </div>
          </div>
          <p className="mt-2 text-[13px] leading-5 text-[color:var(--text-muted)]">
            Введи логин и пароль. Код придёт в Telegram.
          </p>

          <form
            className="mt-6 space-y-3.5"
            action="/auth/request-code"
            method="post"
            onSubmit={() => {
              if (typeof window !== "undefined") {
                const resolvedUsername = username.trim();
                if (resolvedUsername) {
                  window.sessionStorage.setItem(LOGIN_USERNAME_KEY, resolvedUsername);
                }
              }
            }}
          >
            {notice ? (
              <div className="rounded-[22px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-300">
                {notice}
              </div>
            ) : null}
            <div className="space-y-2">
              <label htmlFor="login-username" className="text-sm font-medium text-slate-700 dark:text-slate-300">Логин</label>
              <Input id="login-username" name="username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="login" required className="h-10 text-[13px]" />
            </div>
            <div className="space-y-2">
              <label htmlFor="login-password" className="text-sm font-medium text-slate-700 dark:text-slate-300">Пароль</label>
              <Input id="login-password" name="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" required className="h-10 text-[13px]" />
            </div>
            {error ? <p className="text-sm text-rose-600">{error}</p> : null}
            <Button type="submit" className="w-full">
              Получить код входа
            </Button>
          </form>

          <div className="mt-5 rounded-[20px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-4 py-3 text-[13px] leading-5 text-[color:var(--text-muted)] dark:bg-[var(--surface-muted)]">
            После проверки откроется рабочая сессия панели.
          </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
