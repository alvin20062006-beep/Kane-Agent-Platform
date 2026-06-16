
# Kane / Kāne AI Agent Platform

**Copyright © Kāne / Kane Agent Platform. All rights reserved.**

![Agent Fleet — English UI](docs/images/agent-fleet-en.png)

**Kāne** is a local-first AI agent platform: a control plane for running, coordinating, and observing AI agents. It includes conversations, tasks, skills, credentials, a Local Bridge for external tools, and a Next.js web UI.

**Kanaloa** is the built-in Octopus AI agent shipped with Kāne. It is the default onboard agent identity in the product UI and seed data. Third-party or self-hosted agents can be added alongside Kanaloa, so the platform is not limited to a single model provider or vendor.

This README is intended for a **public repository mirror**. It does not include internal product specifications, private roadmap notes, release checklists, audit logs, or development process documents.

**What this public tree includes:** application source (`apps/*`, `packages/*`), public-safe docs under `docs/` (for example `API.md`, `VERIFY.md`, `LOCAL_BRIDGE.md`), and runtime setup examples (`.env.example`).

**What it excludes:** `docs/PRD.md`, private roadmaps, internal audit/process/checklist documents, `apps/data/*.json`, `.env` / real API keys, and other machine-local runtime data.

---

## What You Get

- **Web app** (`apps/web`)  
  Dashboard, conversations, cockpit, agent fleet, skills, memory, files, settings, and an English/Chinese UI shell.

- **API service** (`apps/api`)  
  FastAPI backend, OpenAPI docs at `/docs`, file-backed persistence by default, and optional PostgreSQL configuration.

- **Local Bridge** (`apps/local-bridge`)  
  A local HTTP bridge that can invoke local commands, forward webhooks, coordinate handoff flows, and return task results to the API.

- **Kanaloa agent runtime**  
  Built-in platform agent with staged capabilities:
  - **P0 — Platform awareness:** reads platform capabilities, registered agents, adapters, and bridge status.
  - **P1 — Action Gateway:** creates tasks, dispatches agents, reads task status/events, and cancels tasks.
  - **P2 — Permission profiles:** supports `owner`, `safe`, and `readonly` profiles for local/private deployments.
  - **P3 — Orchestrator Runtime:** creates master tasks, splits subtasks, selects agents, observes results, retries failures, and summarizes outcomes.

---

## Current Integration Status

| Integration | Status |
|---|---|
| Claude Code | Supported through the Local Bridge / adapter flow. Requires local Claude CLI availability or falls back to handoff behavior. |
| Cursor | Handoff-only / not fully automated. The platform does not pretend Cursor is connected when no supported bridge is available. |
| OpenClaw | Supported when `OPENCLAW_WEBHOOK_URL` or equivalent bridge configuration is provided; otherwise falls back to handoff behavior. |
| Local scripts | Supported through the Local Bridge in local/private deployments. |
| MCP | Not treated as fully implemented unless an actual MCP registry/server is configured. |

---

## Requirements

- Node.js 18+  
  Node.js 20+ is recommended.
- Python 3.10+  
  Python 3.11+ is recommended.

---

## Data Privacy

Runtime data such as conversations, tasks, runs, API profiles, and local state lives under:

```text
apps/data/
```

This directory is ignored by Git by default. A fresh clone does not include another machine’s local tasks, conversations, credentials, or runtime JSON files.

Only this placeholder should be tracked:

```text
apps/data/.gitkeep
```

Do not commit:

```text
apps/data/*.json
.env
.env.*
*.env
```

---

## Quick Start

### Recommended (repository root)

**Requirements:** Node.js 18+ (20+ recommended), Python 3.10+ (3.11+ recommended).  
**Platform note:** root `npm` scripts for API and Bridge assume **Windows** virtualenv paths (`apps/*/.venv/Scripts/python`). On macOS/Linux, use the [manual fallback](#manual-fallback-macos--linux-or-custom-venv) below.

**1. Install Node dependencies and Python environments**

```bash
npm install
npm run setup:api
npm run setup:bridge
```

(`npm run setup` runs both setup scripts.)

**2. Configure the Web app**

Copy the example env file and adjust if needed:

```bash
# PowerShell (from repo root)
Copy-Item .env.example apps/web/.env.local
```

At minimum, `apps/web/.env.local` should contain:

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Export API/Bridge variables in each terminal (or your service manager) from [`.env.example`](.env.example) — see [Environment configuration](#environment-configuration).

**3. Start services (three terminals)**

```bash
npm run dev:api
```

```bash
npm run dev:bridge
```

```bash
npm run dev:web
```

Web dev uses `next dev --webpack` (see `apps/web/package.json`). On Windows with non-ASCII project paths, avoid Turbopack — stick to the default webpack dev server.

**4. Open the UI**

```text
http://127.0.0.1:3000
```

**5. Smoke-check**

With API and Bridge running:

```text
GET http://127.0.0.1:8000/health
```

The health response includes a `startup` object with per-phase timings (import, bootstrap, worker thread). API stderr also logs lines tagged `startup` when `OCTOPUS_STARTUP_LOG` is not disabled.

Offline checks (no servers required):

```bash
npm run verify
```

`npm run verify` runs Web `typecheck` and `lint` (this public mirror does not ship pytest / Playwright suites).

---

### Manual fallback (macOS / Linux or custom venv)

#### API (port 8000)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI: `http://127.0.0.1:8000/docs`

#### Web (port 3000)

```bash
# export NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
cd apps/web
npm run dev
```

If the UI is unresponsive when switching between `localhost` and `127.0.0.1`, align the host with `allowedDevOrigins` in `apps/web/next.config.ts`.

#### Local Bridge (port 8010)

```bash
cd apps/local-bridge
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

See `apps/local-bridge/README.md` for bridge callbacks and adapter behavior.

---

## Environment configuration

Use [`.env.example`](.env.example) as the template. **Do not commit** `.env`, `.env.local`, real API keys, tokens, or `apps/data/*.json`.

| Variable | Used by | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | **Web** (`apps/web/.env.local`) | Browser → API base URL |
| `OCTOPUS_API_PUBLIC_URL` | **API**, **Bridge** | Callback URL Bridge uses to reach API |
| `OCTOPUS_LOCAL_BRIDGE_URL` | **API** | API → Bridge probe / dispatch |
| `OCTOPUS_BRIDGE_SHARED_SECRET` | **API**, **Bridge** | Optional shared auth header |
| `OPENCLAW_WEBHOOK_URL` | **Bridge** | Optional OpenClaw ingest webhook |
| `OCTOPUS_PERSISTENCE` | **API** | `file` (default) or `postgres` |
| `DATABASE_URL` / `OCTOPUS_DATABASE_URL` | **API** | PostgreSQL when persistence is `postgres` |
| `OCTOPUS_LLM_API_KEY`, `LLM_API_KEY` | **API** | LLM provider keys (process env preferred) |
| `LLM_MAX_TOKENS`, `OCTOPUS_LLM_MAX_TOKENS` | **API** | Output cap (`unlimited` = provider default) |

**Web → API**

```text
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

**API ↔ Local Bridge**

```text
OCTOPUS_LOCAL_BRIDGE_URL=http://127.0.0.1:8010
OCTOPUS_API_PUBLIC_URL=http://127.0.0.1:8000
```

Docker Compose (internal network):

```text
OCTOPUS_API_PUBLIC_URL=http://api:8000
```

**LLM keys (API process)**

```text
OCTOPUS_LLM_API_KEY=
LLM_API_KEY=
```

Kāne checks `OCTOPUS_LLM_API_KEY` first, then `LLM_API_KEY`. Prefer process environment over storing keys in local runtime JSON.

**LLM output token cap**

```text
LLM_MAX_TOKENS=unlimited
OCTOPUS_LLM_MAX_TOKENS=unlimited
```

Values such as `unlimited`, `infinite`, `auto`, `none`, `0`, or `-1` mean Kāne will not send `max_tokens` (provider limits apply). Set a positive integer to cap output length, for example `LLM_MAX_TOKENS=8000`.

---

## Docker Compose

Docker Compose is intended for local/private deployment.

```bash
docker compose config
docker compose up --build
```

In Docker Compose mode, the Local Bridge should use:

```text
OCTOPUS_API_PUBLIC_URL=http://api:8000
```

This is for the internal Docker network. It does not mean the project is configured as a public SaaS service.

---

## Security and Limitations

Kāne is currently intended for **local/private deployments**, not as a hardened public multi-tenant SaaS.

Local/private deployment assumptions:

* The owner controls the machine.
* Runtime data stays local unless explicitly exported.
* Local Bridge execution is under the owner’s control.
* `owner` mode is intended for private use.

Before exposing Kāne to the public internet, you must add or configure:

* HTTP authentication
* CORS allowlist
* Reverse proxy access control
* Secret management
* Deployment hardening
* Network-level restrictions
* Rate limiting and monitoring, where appropriate

Public internet exposure is not the default deployment model.

---

## Repository Layout

| Path                | Role                                                 |
| ------------------- | ---------------------------------------------------- |
| `apps/web`          | Next.js frontend                                     |
| `apps/api`          | FastAPI backend                                      |
| `apps/local-bridge` | Local Bridge service                                 |
| `apps/data`         | Local runtime data, ignored by Git except `.gitkeep` |
| `packages/schemas`  | Shared JSON schemas                                  |
| `packages/core`     | Shared Python library (`octopus_core`)               |
| `docs`              | Public-safe documentation                            |

---

## Tests and Verification

**Public mirror (offline; pytest / Playwright suites are not shipped in this tree):**

```bash
npm run verify
```

This runs `typecheck` and `lint`.

**Additional checks:**

```bash
npm run build:web
docker compose config
```

For step-by-step local smoke tests (health, task flow, Bridge callback), see [`docs/VERIFY.md`](docs/VERIFY.md).

After starting services, API health: `GET http://127.0.0.1:8000/health` (includes optional `startup` timing when `OCTOPUS_STARTUP_LOG=1`).

If a script is unavailable in your checkout, check `package.json` and the relevant app-level package files.

---

## Documentation

* [`docs/VERIFY.md`](docs/VERIFY.md) — Local verification guide
* [`docs/API.md`](docs/API.md) — HTTP API overview
* [`docs/LOCAL_BRIDGE.md`](docs/LOCAL_BRIDGE.md) — Local Bridge behavior, environment variables, and safety boundaries
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Architecture and persistence overview
* [`docs/EXTERNAL_AGENT_INTEGRATION.md`](docs/EXTERNAL_AGENT_INTEGRATION.md) — External agent integration status and current limitations

---

## Contributing

Issues and pull requests are welcome.

Please keep changes focused, avoid committing local runtime data, and do not include secrets, private keys, internal planning documents, release checklists, audit logs, or non-public process notes.

---

## License and Commercial Use

Source is publicly visible, but this project is **not** released under an OSI-approved open-source license such as MIT, Apache, or GPL.

You may use this software and may copy, modify, merge, and redistribute the source code or build artifacts as described below, provided that the copyright notice is retained.

Commercial use requires prior contact and agreement with the copyright holder. Commercial use includes, but is not limited to:

* offering the software as a paid service;
* delivering the software as part of a paid product or solution;
* using the software in a client-facing commercial deployment;
* materially equivalent commercial scenarios.

For commercial use, evaluation, collaboration, or additional permissions, please contact the repository owner or open an Issue.
