"use client";

import { MoonStar, ShieldCheck, SunMedium } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useTheme } from "@/components/theme-provider";
import { Button, Card, Input } from "@/components/ui";

const LOGIN_USERNAME_KEY = "amonora-dashboard-login-username";

function VerifyPageContent() {
  const searchParams = useSearchParams();
  const { theme, toggleTheme } = useTheme();
  const username = (() => {
    const queryValue = searchParams.get("username");
    if (queryValue && queryValue !== "undefined") {
      return queryValue;
    }
    if (typeof window !== "undefined") {
      return window.sessionStorage.getItem(LOGIN_USERNAME_KEY) || "";
    }
    return "";
  })();
  const notice = searchParams.get("notice") || "";
  const error = searchParams.get("error") || "";
  const [code, setCode] = useState("");

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div className="absolute inset-0 control-grid opacity-50" />
      <div className="absolute right-5 top-5 z-10">
        <Button variant="ghost" onClick={toggleTheme} type="button">
          {theme === "dark" ? <SunMedium className="mr-2 h-4 w-4" /> : <MoonStar className="mr-2 h-4 w-4" />}
          {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
        </Button>
      </div>

      <Card className="grid w-full max-w-5xl gap-0 overflow-hidden p-0 lg:grid-cols-[1fr_0.9fr]">
        <div className="control-grid relative overflow-hidden bg-[linear-gradient(145deg,#d7dbe0,#c7cdd4_56%,#b4bcc5_100%)] p-7 text-slate-900 dark:bg-[linear-gradient(145deg,#1b1f24,#252a31_56%,#49525b_100%)] dark:text-white lg:p-8">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.22),transparent_26%),radial-gradient(circle_at_bottom_right,rgba(90,101,112,0.08),transparent_18%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.12),transparent_26%),radial-gradient(circle_at_bottom_right,rgba(255,255,255,0.08),transparent_18%)]" />
          <div className="relative">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-[20px] bg-white/42 ring-1 ring-slate-800/10 dark:bg-white/12 dark:ring-white/12">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-800/72 dark:text-white/70">Telegram step</p>
                <h1 className="text-2xl font-semibold tracking-[-0.06em]">Подтверждение входа</h1>
              </div>
            </div>

            <div className="mt-10 space-y-4">
              <h2 className="max-w-xl text-3xl font-semibold tracking-[-0.06em]">Введи код из Telegram.</h2>
              <p className="max-w-md text-[13px] leading-6 text-slate-800/84 dark:text-white/76">
                Код короткоживущий и используется один раз.
              </p>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[22px] border border-slate-800/10 bg-white/52 p-3.5 shadow-[0_16px_28px_-24px_rgba(15,23,42,0.2)] dark:border-white/12 dark:bg-white/8 dark:shadow-none">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-700/68 dark:text-white/56">TTL</div>
                <div className="mt-1.5 text-xl font-semibold tracking-[-0.05em]">5 min</div>
                <div className="mt-1.5 text-[13px] text-slate-700/82 dark:text-white/68">После этого нужен новый код.</div>
              </div>
              <div className="rounded-[22px] border border-slate-800/10 bg-white/52 p-3.5 shadow-[0_16px_28px_-24px_rgba(15,23,42,0.2)] dark:border-white/12 dark:bg-white/8 dark:shadow-none">
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-700/68 dark:text-white/56">Channel</div>
                <div className="mt-1.5 text-xl font-semibold tracking-[-0.05em]">Private</div>
                <div className="mt-1.5 text-[13px] text-slate-700/82 dark:text-white/68">Код уходит в Telegram админа.</div>
              </div>
            </div>
          </div>
        </div>

        <div className="p-6 lg:p-8">
          <div className="mx-auto max-w-md">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[18px] bg-[rgba(255,180,91,0.14)] text-[#8a5209] dark:text-[#ffd7a0]">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[color:var(--accent)]">Telegram verify</p>
              <h2 className="text-2xl font-semibold tracking-[-0.06em] text-slate-950 dark:text-slate-50">Подтверди вход</h2>
            </div>
          </div>

          <form
            className="mt-6 space-y-3.5"
            action="/auth/verify"
            method="post"
            onSubmit={() => {
              if (typeof window !== "undefined") {
                window.sessionStorage.removeItem(LOGIN_USERNAME_KEY);
              }
            }}
          >
            <div className="space-y-2">
              <label htmlFor="verify-username" className="text-sm font-medium text-slate-700 dark:text-slate-300">Администратор</label>
              <Input id="verify-username" name="username" value={username} readOnly className="h-10 text-[13px]" />
            </div>
            {notice ? (
              <div className="rounded-[22px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-500/25 dark:bg-emerald-500/10 dark:text-emerald-300">
                {notice}
              </div>
            ) : null}
            {error ? <p className="text-sm text-rose-600">{error}</p> : null}
            <div className="space-y-2">
              <label htmlFor="verify-code" className="text-sm font-medium text-slate-700 dark:text-slate-300">Код</label>
              <Input id="verify-code" name="code" type="password" value={code} onChange={(event) => setCode(event.target.value)} placeholder="123456" required className="h-10 text-[13px]" />
            </div>
            <Button type="submit" className="w-full">
              Войти в Amonora Control
            </Button>
          </form>

          <div className="mt-5 rounded-[20px] border border-[color:var(--surface-border)] bg-[var(--surface-strong)] px-4 py-3 text-[13px] leading-5 text-[color:var(--text-muted)] dark:bg-[var(--surface-muted)]">
            После подтверждения откроется рабочая сессия панели.
          </div>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <VerifyPageContent />
    </Suspense>
  );
}
