"""Read-only handoff + callback checklist for a platform task."""

from __future__ import annotations

from typing import Any

from ...models import SkillExecuteBody, SkillExecuteResult
from ...settings_env import get_api_public_url
from ...store.repositories import runs_repo, tasks_repo


def execute_handoff_guide_skill(input_payload: dict[str, Any], _body: SkillExecuteBody) -> SkillExecuteResult:
    task_id = str(input_payload.get("task_id") or "").strip()
    if not task_id:
        return SkillExecuteResult(ok=False, error="task_id_required", meta={"kind": "handoff_guide"})

    task = tasks_repo.get(task_id)
    if not task:
        return SkillExecuteResult(ok=False, error="task_not_found", meta={"kind": "handoff_guide"})

    run_id = str(input_payload.get("run_id") or task.last_run_id or "").strip() or None
    run = runs_repo.get(run_id) if run_id else None
    callback = f"{get_api_public_url()}/integrations/bridge/complete"
    integration_path = "manual_agent"
    if run and run.integration_path:
        integration_path = str(run.integration_path)

    handoff_file = f"{task_id}_{run_id or 'run_xxx'}.md"

    return SkillExecuteResult(
        ok=True,
        output={
            "skill_id": "skill_handoff_guide",
            "task_id": task_id,
            "run_id": run_id,
            "task_status": task.status.value,
            "completion_mode": "handoff_callback",
            "callback_url": callback,
            "handoff_file_pattern": handoff_file,
            "integration_path": integration_path,
            "steps": [
                {
                    "id": "locate",
                    "title": "找到 handoff 文件",
                    "detail": f"在 Bridge handoff 目录打开 `{handoff_file}`（frontmatter 含 task_id / callback_url）。",
                },
                {
                    "id": "external",
                    "title": "在外部工具完成",
                    "detail": f"按文件内 Prompt 在 IDE / CLI / Webhook Agent 中执行：{task.title[:120]}",
                },
                {
                    "id": "callback",
                    "title": "POST callback",
                    "detail": (
                        f"POST {callback} ，JSON 含 task_id、run_id、status、output；"
                        f'integration_path 建议 `{integration_path}`。'
                    ),
                },
            ],
            "bridge_url": f"/local-bridge?taskId={task_id}",
            "task_url": f"/tasks/{task_id}",
        },
        meta={"kind": "handoff_guide"},
    )
