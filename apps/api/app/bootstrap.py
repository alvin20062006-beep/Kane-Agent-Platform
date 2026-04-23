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


def bootstrap_if_empty() -> None:
    """
    Seed empty file/DB stores with minimal defaults (built-in agent, builtin skills, one global policy).
    No sample external agents, tasks, reports, accounts, credentials, or memory rows.
    """

    if not agents_repo.list():
        for a in seed_agents():
            agents_repo.upsert(a)

    if not tasks_repo.list():
        for t in seed_tasks():
            tasks_repo.upsert(t)

    if not skills_repo.list():
        for s in seed_skills():
            if skill_is_user_visible(s):
                skills_repo.upsert(s)
    else:
        existing_ids = {s.skill_id for s in skills_repo.list()}
        for s in seed_skills():
            if not skill_is_user_visible(s):
                continue
            if s.skill_id not in existing_ids:
                skills_repo.upsert(s)

    if not accounts_repo.list():
        for a in seed_accounts():
            accounts_repo.upsert(a)

    if not credentials_repo.list():
        for c in seed_credentials():
            credentials_repo.upsert(c)

    if not memory_repo.list():
        for m in seed_memory():
            memory_repo.upsert(m)

    if not policies_repo.list():
        for p in seed_policies():
            policies_repo.upsert(p)

    if not reports_repo.list():
        for r in seed_reports():
            reports_repo.upsert(r)
