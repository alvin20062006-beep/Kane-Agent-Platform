# Kāne Agent Platform (Beta)

**Kāne** is a local-first **AI agent platform**: a control plane for running and observing agents, with conversations, tasks, skills, credentials, an optional **Local Bridge** for external tools (CLI / webhook / handoff flows), and a Next.js web UI.

**Kanaloa** is the **built-in Octopus AI agent** shipped with Kāne—the default onboard agent identity in the product UI and seed data. Third-party or self-hosted agents can be added alongside Kanaloa; the platform is not limited to a single vendor model.

This README is intended for a **public** repository mirror. It does not include internal product specs or release checklists.

## What you get

- **Web app** (`apps/web`): dashboard, conversations, cockpit, agent fleet, skills, memory, files, settings — with English/Chinese UI shell.
- **API** (`apps/api`): FastAPI service, OpenAPI at `/docs`, file-backed persistence by default.
- **Local Bridge** (`apps/local-bridge`): small HTTP service that can invoke local commands, forward webhooks, and coordinate handoff/callback patterns with the API.

## Requirements

- Node.js 18+ (20+ recommended)
- Python 3.10+ (3.11+ recommended)

## Quick start (development)

### 1. Install dependencies (repo root)

```bash
npm install
```

### 2. API (port 8000)

```bash
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Web (port 3000)

From repo root, set the API URL for the browser (example):

```bash
# Windows PowerShell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
cd apps/web
npm run dev
```

Open `http://127.0.0.1:3000` (or the URL printed by Next.js).  
If the UI is unresponsive when using `localhost` vs `127.0.0.1`, align the host with `allowedDevOrigins` in `apps/web/next.config.ts`.

### 4. Local Bridge (optional, typical port 8010)

```bash
cd apps/local-bridge
python -m venv .venv
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

See `apps/local-bridge/README.md` for environment variables and callback URLs.

## Configuration (high level)

- **Web → API**: `NEXT_PUBLIC_API_BASE_URL` (build/runtime).
- **API → Bridge**: `OCTOPUS_LOCAL_BRIDGE_URL` and related vars (see root `.env.example` if present).
- **Secrets**: do not commit `.env` files. Credential records in the API are **write-only** for secret material in beta builds.

## Security and limitations (read this)

This project is a **beta** for local / lab use, not a hardened multi-tenant SaaS:

- No production-grade OAuth app onboarding, billing, or KMS-backed secret storage.
- File-backed data is convenient for development; use PostgreSQL only when you intentionally configure it.
- Review outbound skills (e.g. HTTP) and execution policies before enabling them in untrusted environments.

## Repository layout

| Path | Role |
|------|------|
| `apps/web` | Next.js frontend |
| `apps/api` | FastAPI backend |
| `apps/local-bridge` | Bridge service |
| `packages/schemas` | Shared JSON schemas |
| `packages/core` | Shared TypeScript utilities |

## Tests

From `apps/api` (with venv active):

```bash
pytest
```

From `apps/web`:

```bash
npm run build
```

## Contributing

Issues and PRs are welcome. Keep changes focused; match existing code style.

## License

**All rights reserved.** This repository and its contents are **not** released under an open-source license.

- **English:** No permission is granted to use, copy, modify, merge, publish, distribute, sublicense, or sell the software for any purpose—including **commercial use**—unless you obtain **prior written permission** from the copyright holder(s).
- **中文：** 保留所有权利。任何使用、复制、修改或**商用**，均须在事先取得著作权人**书面许可**；本仓库**不以** MIT 等开源许可发布。

For licensing inquiries (evaluation, partnership, etc.), open an issue or contact the repository owner.

---

## Publishing checklist (what belongs in a **public** clone)

**Safe to include:** application source under `apps/*`, `packages/*`, root tooling (`package.json`, etc.), generic deployment hints, and this file copied to `README.md`.

**Omit or redact:** private backlog/specs (e.g. internal PRD or roadmap drafts), personal validation checklists, private GitHub URLs, credentials, and local `apps/data` or `.env` files. Prefer `.gitignore` as already defined in this repo for runtime data.

**Automated export (Windows):** from the private workspace, run `gh auth login` once, then `powershell -ExecutionPolicy Bypass -File scripts/publish-public-to-github.ps1` to copy a filtered tree, create `https://github.com/alvin20062006-beep/Kane-Agent-Platform` if missing, and push `main`. Use `-ExportOnly` to only build the temp export + git commit (no remote).
