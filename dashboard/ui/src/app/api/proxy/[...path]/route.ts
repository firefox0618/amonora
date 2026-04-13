import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PRIVATE_DASHBOARD_BACKEND || "http://127.0.0.1:8088";

async function proxy(request: NextRequest, paramsPromise: Promise<{ path: string[] }>) {
  try {
    const { path } = await paramsPromise;
    const target = new URL(`${BACKEND_URL}/${path.join("/")}`);
    target.search = request.nextUrl.search;

    const publicHost = request.headers.get("host") || request.nextUrl.host;
    const publicProto = request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "");
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("connection");
    headers.delete("content-length");
    headers.delete("accept-encoding");
    headers.set("x-forwarded-host", publicHost);
    headers.set("x-forwarded-proto", publicProto);
    headers.set("accept", "application/json");
    headers.set("accept-encoding", "identity");

    const init: RequestInit = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (!["GET", "HEAD"].includes(request.method)) {
      const requestContentType = request.headers.get("content-type") || "";
      if (requestContentType.includes("application/json")) {
        const bodyText = await request.text();
        if (bodyText.length > 0) {
          init.body = bodyText;
        }
      } else {
        const body = await request.arrayBuffer();
        if (body.byteLength > 0) {
          init.body = body;
        }
      }
    }

    const upstream = await fetch(target, init);
    const contentType = upstream.headers.get("content-type") || "";

    if (!contentType.includes("application/json") && ["GET", "HEAD"].includes(request.method)) {
      const response = new NextResponse(request.method === "HEAD" ? null : upstream.body, { status: upstream.status });
      if (contentType) {
        response.headers.set("content-type", contentType);
      }
      for (const headerName of ["content-disposition", "cache-control", "etag", "last-modified", "x-content-type-options"]) {
        const value = upstream.headers.get(headerName);
        if (value) {
          response.headers.set(headerName, value);
        }
      }
      upstream.headers.forEach((value, key) => {
        if (key.toLowerCase() === "set-cookie") {
          response.headers.append("set-cookie", value);
        }
      });
      return response;
    }

    const bodyText = request.method === "HEAD" ? "" : await upstream.text();

    if (!contentType.includes("application/json")) {
      return NextResponse.json(
        {
          ok: false,
          error: `proxy_non_json:${bodyText.slice(0, 240) || "empty_response"}`,
        },
        { status: 502 },
      );
    }

    const response = new NextResponse(bodyText, { status: upstream.status });
    response.headers.set("content-type", "application/json; charset=utf-8");

    upstream.headers.forEach((value, key) => {
      if (key.toLowerCase() === "set-cookie") {
        response.headers.append("set-cookie", value);
      }
    });

    return response;
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: `proxy_runtime_failed:${error instanceof Error ? error.message : "unknown"}`,
      },
      { status: 502 },
    );
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context.params);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context.params);
}
