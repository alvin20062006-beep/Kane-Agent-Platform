import { getApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

async function proxy(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (!(path[0] === "api" && path[1] === "v1") && path.join("/") !== "health") {
    return Response.json({ detail: "Unknown API path" }, { status: 404 });
  }
  const incoming = new URL(req.url);
  if (!["GET", "HEAD"].includes(req.method) && req.headers.get("origin")) {
    let originHost: string;
    try { originHost = new URL(req.headers.get("origin")!).host; }
    catch { return Response.json({ detail: "Invalid request origin" }, { status: 403 }); }
    if (originHost !== req.headers.get("host")) return Response.json({ detail: "Cross-origin request rejected" }, { status: 403 });
  }
  const headers = new Headers({ Accept: req.headers.get("accept") ?? "application/json" });
  const authorization = req.headers.get("authorization");
  const token = req.headers.get("x-api-key");
  if (authorization) headers.set("Authorization", authorization);
  if (token) headers.set("X-Api-Key", token);
    if (req.method === "POST" || req.method === "PUT" || req.method === "PATCH") headers.set("Content-Type", "application/json");
  try {
    const response = await fetch(`${getApiBaseUrl()}/${path.map(encodeURIComponent).join("/")}${incoming.search}`, {
      method: req.method,
      headers,
      body: ["POST", "PUT", "PATCH"].includes(req.method) ? await req.text() : undefined,
      cache: "no-store",
      signal: req.signal,
    });
    return new Response(response.body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store", "X-Accel-Buffering": "no" },
    });
  } catch {
    return Response.json({ detail: "Kane API is unavailable" }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
