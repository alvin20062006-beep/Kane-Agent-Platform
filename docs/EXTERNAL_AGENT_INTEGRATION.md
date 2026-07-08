# External Agent Integration

Kane v2.0.0 integrates external or local agents through the API worker and Local Bridge. This document describes current behavior only.

## Integration Matrix

| Agent / adapter | Path | When it counts as automated |
|---|---|---|
| Builtin Kanaloa | API worker | Does not require Bridge. Task, run, and run steps should converge to terminal status. |
| Codex CLI | API -> Bridge `/v1/execute`, `adapter_id=codex_cli` | Only when the local CLI exists and the OS permits execution. Permission errors are recorded as real failures. |
| Cursor | API -> Bridge `/v1/execute`, `adapter_id=cursor_cli` | Handoff-oriented in v2.0.0. Kane writes handoff work and waits for real completion. |
| Claude Code | API -> Bridge `/v1/execute`, `adapter_id=claude_code` | Uses local CLI when available; otherwise handoff. |
| OpenClaw HTTP | Bridge posts to `OPENCLAW_WEBHOOK_URL` | Automated only when webhook is configured and returns a real success response. |
| Local script | Bridge `subprocess` path | Trusted local use only, with explicit configured command metadata. |

## Completion Callback

External or handoff flows can complete a run through:

```text
POST {OCTOPUS_API_PUBLIC_URL}/integrations/bridge/complete
```

Example body:

```json
{
  "task_id": "task_...",
  "run_id": "run_...",
  "status": "succeeded",
  "output": "result text",
  "error": null,
  "integration_path": "manual_handoff"
}
```

If `OCTOPUS_BRIDGE_SHARED_SECRET` is configured, include:

```text
X-Octopus-Bridge-Key: <secret>
```

The environment variable and header names are retained for compatibility in v2.0.0.

## Honest Status Rules

- Missing CLI means unavailable or handoff, not fake online.
- OS permission errors are failures or needs-attention states, not success.
- Cursor handoff is not full headless execution.
- Webhook success requires a real 2xx response from the configured endpoint.
- High-risk local command execution should remain owner-controlled and local/private.

## Runtime Data

External agent handoff files and bridge results live under:

```text
apps/local-bridge/data/
```

API task, run, run-step, verifier, repair, memory, and compiler records live under:

```text
apps/data/
```

Both directories are ignored by Git. Do not commit runtime JSON, local test tasks, handoff files, logs, or secrets.
