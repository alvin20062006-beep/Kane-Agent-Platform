import { apiGet } from "@/lib/api";
import type { ListResponse } from "@/lib/octopus-types";

type Report = {
  report_id: string;
  type: string;
  title: string;
  created_at: string;
  content: string;
  is_mock: boolean;
};

export default async function ReportsPage() {
  let data: ListResponse<Report> | null = null;
  let error: unknown = null;
  try {
    data = await apiGet<ListResponse<Report>>("/reports");
  } catch (e) {
    error = e;
  }
  const errorText = error ? (error instanceof Error ? error.message : String(error)) : null;
  const { ReportsClient } = await import("./reports-client");
  return <ReportsClient items={data?.items ?? null} errorText={errorText} />;
}
