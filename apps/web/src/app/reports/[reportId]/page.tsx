import { apiGet } from "@/lib/api";

export default async function ReportDetailPage({
  params,
}: {
  params: Promise<{ reportId: string }>;
}) {
  const { reportId } = await params;
  let data: unknown = null;
  let error: unknown = null;

  try {
    data = await apiGet(`/reports/${encodeURIComponent(reportId)}`);
  } catch (e) {
    error = e;
  }

  const errorText = error ? (error instanceof Error ? error.message : String(error)) : null;
  const { ReportDetailClient } = await import("./report-detail-client");
  return <ReportDetailClient reportId={reportId} data={data} errorText={errorText} />;
}

