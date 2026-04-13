import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PRIVATE_DASHBOARD_BACKEND || "http://127.0.0.1:8088";
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

function publicOrigin(request: NextRequest) {
  const host = request.headers.get("host") || request.nextUrl.host;
  const proto = request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "");
  return `${proto}://${host}`;
}

function redirectPath(path: string, params: Record<string, string>) {
  const url = new URL(`${BASE_PATH}${path}`, "http://localhost");
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      url.searchParams.set(key, value);
    }
  });
  return `${url.pathname}${url.search}`;
}

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const username = String(formData.get("username") || "").trim();
  const password = String(formData.get("password") || "");

  if (!username || !password) {
      return NextResponse.redirect(
      new URL(
        redirectPath("/login", {
          username,
          error: "Введи логин и пароль.",
        }),
        publicOrigin(request),
      ),
      303,
    );
  }

  try {
    const upstream = await fetch(`${BACKEND_URL}/dashboard/api/v2/auth/request-code`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify({ username, password }),
    });

    const payload = (await upstream.json().catch(() => null)) as
      | { ok?: boolean; error?: string; notice?: string; data?: { username?: string } }
      | null;

    if (!upstream.ok || !payload?.ok) {
      return NextResponse.redirect(
        new URL(
          redirectPath("/login", {
            username,
            error: payload?.error || "Не удалось отправить код. Попробуй ещё раз.",
          }),
          publicOrigin(request),
        ),
        303,
      );
    }

    const resolvedUsername = (payload.data?.username || username).trim();
    const notice = payload.notice || "Код отправлен в @amonora_support_bot";

    return NextResponse.redirect(
      new URL(
        redirectPath("/verify", {
          username: resolvedUsername,
          notice,
        }),
        publicOrigin(request),
      ),
      303,
    );
  } catch {
    return NextResponse.redirect(
      new URL(
        redirectPath("/login", {
          username,
          error: "Не удалось связаться с сервером. Попробуй ещё раз.",
        }),
        publicOrigin(request),
      ),
      303,
    );
  }
}
