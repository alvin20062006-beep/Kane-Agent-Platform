# Local Bridge

The Local Bridge is a small FastAPI service that runs on the user's machine or trusted local network. Kane API uses it for local agent adapters and handoff flows.

Default URL:

```text
http://127.0.0.1:8010
```

## Start

From the repository root:

```bash
npm run dev:bridge
```

Or start the whole local stack:

```bash
npm run dev:stack
```

## Health

```text
GET http://127.0.0.1:8010/health
GET http://127.0.0.1:8010/v1/status
```

`/health` is lightweight. `/v1/status` reports registered bridge agents, handoff directory state, and adapter availability such as Codex, Cursor, and Claude CLI detection.

## Environment

| Variable | Purpose |
|---|---|
| `OCTOPUS_API_PUBLIC_URL` | API callback URL used by Bridge, default `http://127.0.0.1:8000` |
| `OCTOPUS_BRIDGE_SHARED_SECRET` | Optional shared secret for protected Bridge operations |
| `OPENCLAW_WEBHOOK_URL` | Optional OpenClaw webhook target |

The `OCTOPUS_*` names are retained for v2.0.0 compatibility.

If `OCTOPUS_BRIDGE_SHARED_SECRET` is set, requests use:

```text
X-Octopus-Bridge-Key: <secret>
```

This compatibility header is a lightweight local guard. It is not a substitute for full production authentication, mTLS, or network isolation.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Bridge health |
| GET | `/v1/status` | Adapter and handoff status |
| POST | `/agents/register` | Register bridge-side agent metadata |
| POST | `/agents/heartbeat` | Record heartbeat |
| GET | `/agents` | List bridge-side agents |
| GET | `/agents/{agent_id}` | Read bridge-side agent |
| POST | `/v1/execute` | Execute or hand off a task for a supported adapter |
| POST | `/tasks/result` | Submit a task result and optionally callback to API |
| GET | `/tasks/results` | List recent bridge results |

## Adapter Boundaries

| Adapter | v2.0.0 behavior |
|---|---|
| `codex_cli` | Uses local Codex CLI when available and permitted by the OS. Permission errors are reported honestly. |
| `cursor_cli` | Handoff-oriented. Writes handoff files and waits for real human/tool completion. |
| `claude_code` | Uses local Claude CLI when available; otherwise falls back to handoff. |
| `openclaw_http` | Posts JSON to `OPENCLAW_WEBHOOK_URL` when configured; otherwise uses handoff. |
| `local_script` | Runs configured local commands in trusted local environments only. |
| `http_agent` / `cli_agent` | Generic adapter paths when configured by agent metadata. |

Bridge must not pretend an unavailable local tool is online. It should return a real adapter status or a real failure.

## Handoff Files

Handoff files are written under:

```text
apps/local-bridge/data/handoffs/
```

This directory is runtime data and is ignored by Git. Do not commit handoff files.

## Safety

The Bridge can interact with local CLIs or local shell commands. Use it only on machines and networks you trust. Do not expose the Bridge directly to the public internet without proper authentication, network controls, and operational hardening.
