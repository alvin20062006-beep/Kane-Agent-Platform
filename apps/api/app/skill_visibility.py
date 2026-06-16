"""Filter catalog skills/reports exposed to users (hide legacy internal markers)."""

from __future__ import annotations

from .models import Report, Skill

LEGACY_HIDDEN_TITLE_MARKER = "[mock]"


def skill_is_user_visible(skill: Skill) -> bool:
    blob = f"{skill.skill_id} {skill.name or ''} {skill.description or ''}"
    return LEGACY_HIDDEN_TITLE_MARKER not in blob.lower()


def report_is_user_visible(report: Report) -> bool:
    if getattr(report, "is_draft", getattr(report, "is_mock", False)):
        return False
    title = report.title or ""
    return LEGACY_HIDDEN_TITLE_MARKER not in title.lower()
