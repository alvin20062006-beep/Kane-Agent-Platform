import { ApiError } from "@/components/api-error";
import { PageTitleI18n } from "@/components/page-title-i18n";
import { apiGet } from "@/lib/api";
import type { ListResponse } from "@/lib/octopus-types";

import { FilesClient, type FileArtifact } from "./files-client";

export default async function FilesPage() {
  let resp: ListResponse<FileArtifact>;
  try {
    resp = await apiGet<ListResponse<FileArtifact>>("/files");
  } catch (error) {
    return (
      <div className="space-y-6 p-6">
        <PageTitleI18n titleKey="files.title" subtitleKey="files.subtitle" />
        <ApiError error={error} />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <PageTitleI18n titleKey="files.title" subtitleKey="files.subtitle" />
      <FilesClient initialFiles={resp.items ?? []} />
    </div>
  );
}
