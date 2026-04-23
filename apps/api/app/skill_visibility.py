"""Filter catalog skills/reports exposed to users (Beta: hide [MOCK] markers)."""

from __future__ import annotations

from .models import Report, Skill

MOCK_MARKER = "[mock]"


def skill_is_user_visible(skill: Skill) -> bool:
    blob = f"{skill.skill_id} {skill.name or ''} {skill.description or ''}"
    return MOCK_MARKER not in blob.lower()


def report_is_user_visible(report: Report) -> bool:
    if getattr(report, "is_mock", False):
        return False
    title = report.title or ""
    return MOCK_MARKER not in title.lower()
