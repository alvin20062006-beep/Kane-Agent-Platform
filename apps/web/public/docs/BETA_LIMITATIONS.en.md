# Beta Limitations — Honest Boundaries for the Public Free Beta

This repository's **Public Free Beta** is described for external readers by the root [`README.md`](../../../../README.md) and this document (see also [`docs/BETA_LIMITATIONS.md`](../../../../docs/BETA_LIMITATIONS.md)). Internal spec sources and release checklists are not shipped in the public mirror.

---

## What this Beta has closed out

- **No `[MOCK]` skill entries**: seeds and `apps/api/data/skills.json` are clean; `skill_visibility` plus the list APIs (`/v1/skills`, v2 skills) filter `[MOCK]` / `is_mock`; running an invisible skill returns 404.
- **No placeholder mock reports**: the `reports` list API and the data layer share a single visibility filter.
- **Standalone `/notifications`**: `apps/web/src/app/notifications/page.tsx` calls the real `GET /notifications/channels`; enable/disable hits `POST /notifications/channels` (if your env forbids writes or the endpoint has shifted, follow the page's own notice).
- **Settings + navigation**: `Settings` keeps the notifications summary with a "See all" link to `/notifications`; the sidebar has a **Notifications** entry (bell icon).
- **Default execution policy**: the repo default is `mode: auto`, `is_mock: false`, so runs do not stall on `waiting_approval` after a clean install. Tighten to `confirm` / `notify` under `/policies` as needed.
- **Automated verification**: the current session has executed `npm run build:web` (pass), `pytest` under `apps/api` (pass), and `.\scripts\run-web-prod-e2e.ps1` (pass, including the local agent control plane suite).

---

## What's real (runnable, demo-ready)

- **Execution modes** (Chinese UI labels: **内置直连** · **外部直连** · **统筹执行** · **追踪执行**):
  - `direct_agent` (built-in) — **Direct (built-in)** / 内置直连: Kanaloa runs a turn via its activated LLM profile or deterministic fallback
  - `direct_agent` (external) — **Direct (external)** / 外部直连: platform acts as bridge / memory store / monitor; the external agent does the work
  - `commander` — **Coordinated execution** / 统筹执行: Kanaloa plans and orchestrates (Kanaloa-only)
  - `pilot` — **Tracked execution** / 追踪执行: Kanaloa tracks lifecycle and emits events while the user drives (Kanaloa-only)
- **Task lifecycle**: `POST /tasks` → `assign` → `run` → (optional) `retry` / `fail`
- **File persistence**: `apps/api/data/*.json` (fine for Beta; not enterprise-grade DB)
- **Optional PostgreSQL**: `OCTOPUS_PERSISTENCE=postgres` + Alembic; schema is a JSONB compatibility layer, not the final table split from PRD (see [`docs/DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md))
- **Built-in executor**: `octopus_builtin` runs synchronously (structured output, deterministic when no LLM is bound)
- **Local Bridge**: `POST /v1/execute` is a real HTTP call; **Claude Code** uses `claude -p` if the CLI is present, otherwise a **handoff** file
- **OpenClaw**: real HTTP POST when `OPENCLAW_WEBHOOK_URL` is set, handoff otherwise
- **Cursor**: we do **not** claim full headless automation; default is **handoff** with an optional `cursor --version` detection
- **Callbacks**: `POST /integrations/bridge/complete` resolves tasks parked in `waiting_approval`
- **Monitoring**: `GET /metrics`, `GET /watchdog` (beta-grade heuristics)

---

## Beta-grade / not production-hardened (do not market as GA)

- **No** OAuth / third-party developer app registration flow
- **No** billing / subscription
- **No** production secret vault (KMS / Keychain) or full multi-tenant isolation
- **No** enterprise audit or fine-grained RBAC
- Bridge auth is only an optional shared secret (`OCTOPUS_BRIDGE_SHARED_SECRET`)
- Notification delivery has **no** production SLA; channel management sits inside Beta boundaries

---

## Placeholder / not yet claimed

- Fully "remote-controlled" Cursor / OpenClaw / any desktop GUI (unless your environment actually has the CLI / webhook)
- App Store / desktop installer distribution
- Production-grade HA, backups, compliance certifications
- Full mobile-native app and pixel-perfect PRD five-zone cockpit

---

## Data migration path (beyond file storage)

The next phase recommends PostgreSQL + a migration tool; task / event / run / log tables follow [`docs/DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md).

---

## Summary — do not market as GA

Nothing listed above under **"Beta-grade / not production-hardened"** or **"Placeholder / not yet claimed"** may be marketed as "GA / production-ready / fully complete".
