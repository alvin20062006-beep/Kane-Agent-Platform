import { ApiError } from "@/components/api-error";
import { PageTitleI18n } from "@/components/page-title-i18n";
import { apiGet } from "@/lib/api";
import type { Agent, ListResponse, Task } from "@/lib/octopus-types";

import { TasksClient } from "./tasks-client";

export default async function TasksPage() {
  try {
    const [tasks, agents] = await Promise.all([
      apiGet<ListResponse<Task>>("/tasks"),
      apiGet<ListResponse<Agent>>("/agents"),
    ]);

    return (
      <div className="p-6 space-y-6">
        <PageTitleI18n titleKey="tasks.title" subtitleKey="tasks.subtitle" />
        <TasksClient initialTasks={tasks.items} agents={agents.items} />
      </div>
    );
  } catch (error) {
    return (
      <div className="p-6 space-y-6">
        <PageTitleI18n titleKey="tasks.title" subtitleKey="tasks.subtitle" />
        <ApiError error={error} />
      </div>
    );
  }
}
