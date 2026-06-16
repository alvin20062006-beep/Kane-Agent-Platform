from __future__ import annotations

from .seed_data import (
    seed_accounts,
    seed_agents,
    seed_credentials,
    seed_memory,
    seed_policies,
    seed_reports,
    seed_skills,
    seed_tasks,
)
from .skill_visibility import skill_is_user_visible
from .startup_timing import mark
from .store.repositories import (
    accounts_repo,
    agents_repo,
    credentials_repo,
    memory_repo,
    policies_repo,
    reports_repo,
    skills_repo,
    tasks_repo,
)

_SKILLS_MERGE_DONE = False


def bootstrap_if_empty() -> None:
    """
    Seed empty file/DB stores with minimal defaults (built-in agent, builtin skills, one global policy).
    No sample external agents, tasks, reports, accounts, credentials, or memory rows.
    """
    global _SKILLS_MERGE_DONE

    mark("bootstrap.begin")

    if not agents_repo.list():
        for a in seed_agents():
            agents_repo.upsert(a)
    mark("bootstrap.agents")

    if not tasks_repo.list():
        for t in seed_tasks():
            tasks_repo.upsert(t)
    mark("bootstrap.tasks")

    existing_skills = skills_repo.list()
    if not existing_skills:
        for s in seed_skills():
            if skill_is_user_visible(s):
                skills_repo.upsert(s)
    elif not _SKILLS_MERGE_DONE:
        # Once per process: add newly shipped builtin skills without re-scanning on every reload.
        existing_ids = {s.skill_id for s in existing_skills}
        for s in seed_skills():
            if not skill_is_user_visible(s):
                continue
            if s.skill_id not in existing_ids:
                skills_repo.upsert(s)
        _SKILLS_MERGE_DONE = True
    mark("bootstrap.skills")

    if not accounts_repo.list():
        for a in seed_accounts():
            accounts_repo.upsert(a)
    mark("bootstrap.accounts")

    if not credentials_repo.list():
        for c in seed_credentials():
            credentials_repo.upsert(c)
    mark("bootstrap.credentials")

    if not memory_repo.list():
        for m in seed_memory():
            memory_repo.upsert(m)
    mark("bootstrap.memory")

    if not policies_repo.list():
        for p in seed_policies():
            policies_repo.upsert(p)
    mark("bootstrap.policies")

    if not reports_repo.list():
        for r in seed_reports():
            reports_repo.upsert(r)
    mark("bootstrap.reports")
