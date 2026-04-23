from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from ..id_utils import new_id
from ..models import Report
from ..store.repositories import reports_repo, runs_repo, task_events_repo, tasks_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def generate_comparison_report(*, limit_runs: int = 200) -> Report:
    """
    Generate a real report from persisted runs/events (beta).
    - Success rate by agent
    - Failure reasons distribution
    - Handoff waiting counts
    """
    runs = runs_repo.list()
    runs.sort(key=lambda r: r.started_at, reverse=True)
    runs = runs[:limit_runs]

    by_agent_total: Counter[str] = Counter()
    by_agent_ok: Counter[str] = Counter()
    by_agent_fail: Counter[str] = Counter()
    fail_reasons: Counter[str] = Counter()
    integration_paths: Counter[str] = Counter()

    for r in runs:
        agent = r.agent_id or "unknown"
        by_agent_total[agent] += 1
        if r.status == "succeeded":
            by_agent_ok[agent] += 1
        if r.status == "failed":
            by_agent_fail[agent] += 1
            fail_reasons[r.error or "unknown_error"] += 1
        integration_paths[r.integration_path or "unknown"] += 1

    tasks = tasks_repo.list()
    waiting = sum(1 for t in tasks if t.status.value == "waiting_approval")

    # basic latencies (where possible)
    latencies: dict[str, list[float]] = defaultdict(list)
    for r in runs:
        if not r.finished_at:
            continue
        try:
            s = datetime.fromisoformat(r.started_at.replace("Z", "+00:00"))
            f = datetime.fromisoformat(r.finished_at.replace("Z", "+00:00"))
            latencies[r.agent_id or "unknown"].append((f - s).total_seconds())
        except Exception:
            continue

    def _fmt_latency(xs: list[float]) -> str:
        if not xs:
            return "n/a"
        xs2 = sorted(xs)
        p50 = xs2[len(xs2) // 2]
        return f"p50={p50:.2f}s n={len(xs2)}"

    lines: list[str] = []
    lines.append("Octopus Platform — Real Comparison Report (beta)")
    lines.append(f"generated_at: {_now_iso()}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- runs_analyzed: {len(runs)}")
    lines.append(f"- tasks_total: {len(tasks)}")
    lines.append(f"- tasks_waiting_external: {waiting}")
    lines.append("")
    lines.append("## Success rate by agent")
    for agent, total in by_agent_total.most_common():
        ok = by_agent_ok.get(agent, 0)
        fail = by_agent_fail.get(agent, 0)
        rate = (ok / total * 100.0) if total else 0.0
        lines.append(f"- {agent}: ok={ok} fail={fail} total={total} success_rate={rate:.1f}% latency({_fmt_latency(latencies.get(agent, []))})")
    lines.append("")
    lines.append("## Failure reasons (top)")
    for reason, cnt in fail_reasons.most_common(15):
        lines.append(f"- {reason}: {cnt}")
    if not fail_reasons:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Integration paths")
    for p, cnt in integration_paths.most_common():
        lines.append(f"- {p}: {cnt}")
    lines.append("")

    # Small event sample
    events = task_events_repo.list()
    events.sort(key=lambda e: e.created_at, reverse=True)
    sample = events[:10]
    lines.append("## Latest task events (sample)")
    for e in sample:
        lines.append(f"- {e.created_at} {e.task_id} {e.type} {e.message or ''}".rstrip())

    report = Report(
        report_id=new_id("rpt"),
        type="comparison",
        title="Real runs comparison report",
        created_at=_now_iso(),
        content="\n".join(lines),
        is_mock=False,
    )
    reports_repo.upsert(report)
    return report

