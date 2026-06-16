"use client";

import { useEffect, useState } from "react";

type Status = "unknown" | "ok" | "down";

export function ApiStatusPill() {
  const [status, setStatus] = useState<Status>("unknown");

  useEffect(() => {
    let cancelled = false;
    const base =
      process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

    fetch(`${base}/health`)
      .then((response) =>
        response.ok ? response.json() : Promise.reject(new Error("bad status"))
      )
      .then((json) => {
        if (!cancelled) {
          setStatus(json?.status === "ok" ? "ok" : "down");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("down");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const className =
    status === "ok"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : status === "down"
        ? "bg-rose-50 text-rose-700 ring-rose-200"
        : "bg-zinc-50 text-zinc-700 ring-zinc-200";

  const label =
    status === "ok" ? "API: OK" : status === "down" ? "API: DOWN" : "API: ...";

  return <div className={`rounded-full px-2 py-1 text-xs ring-1 ${className}`}>{label}</div>;
}
