import { NextResponse } from "next/server";

import { getApiBaseUrl } from "@/lib/api";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const apiBase = getApiBaseUrl();
  const url = `${apiBase}/${path.join("/")}`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": req.headers.get("content-type") ?? "application/json",
    },
    body: req.body ? await req.text() : undefined,
    cache: "no-store",
  });

  // If backend returns JSON, keep it; otherwise just pass status.
  const text = await res.text();
  const isJson = (res.headers.get("content-type") ?? "").includes("application/json");

  if (isJson) {
    return NextResponse.json(JSON.parse(text), { status: res.status });
  }
  return new NextResponse(text, { status: res.status });
}

