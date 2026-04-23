# Local Multi-Agent Control Plane — User Guide (Beta)

This guide targets **users** of the Kāne & Kanaloa platform (not just readers of the source code): what each entry point does, how to wire up the four kinds of external / local agents, how to test-run, and how to troubleshoot. Technical details and API inventory live in [`docs/EXTERNAL_AGENT_INTEGRATION.md`](docs/EXTERNAL_AGENT_INTEGRATION.md) and [`docs/API_ROUTE_INVENTORY.md`](docs/API_ROUTE_INVENTORY.md). Beta boundaries: [`docs/BETA_LIMITATIONS.md`](docs/BETA_LIMITATIONS.md).

---

## 1. What each entry point does

| Path | Purpose | What you can do | Category |
|------|---------|-----------------|----------|
| **`/local-bridge`** | Check whether **Local Bridge** is reachable and configured correctly | Inspect status, run the one-click **probe**, read error hints | **Test / troubleshoot** (bridge side) |
| **`/agents/add`** | **Register a new agent** on the platform | Pick a template, fill minimal config, submit; optionally register it with the Bridge | **Add agent** |
| **`/agent-fleet`** | **Overview** of registered agents | Browse, filter, drill into a single agent | **Status view** (fleet perspective) |
| **`/agent-fleet/[id]`** | **Details and config** for one agent | Inspect integration mode / channels / control depth; editable fields **persist via PATCH**; **test connection / test run** | **Configure agent** + **test run** |
| **`/cockpit`** | Cockpit: **dispatch work** from a conversational entry | Create tasks and drive them through assign / run | **Dispatch** (one of several entry points) |
| **`/tasks`** | **Task list and creation** | Create tasks, track status, open details to view timeline and outputs | **Dispatch** + **status view** |
| **`/settings`** | Global settings: API profiles, notification summaries, etc. | Configure model + keys, jump to notifications page | **Environment config** (account / model level) |
| **`/notifications`** | Notification channel list and management | Inspect channels, enable/disable (within beta limits) | **Status view** (notifications side) |

**Mnemonic**: add a teammate at **`/agents/add`**, review the roster at **`/agent-fleet`**, edit one at **`/agent-fleet/[id]`**, fix bridge issues at **`/local-bridge`**, and drive the work from **`/tasks`** or **`/cockpit`**.

---

## 2. Execution modes (matched with the UI)

The UI and backend share four execution modes. **Chinese product labels** (when the UI is in Chinese): **内置直连** · **外部直连** · **统筹执行** · **追踪执行**. English UI uses the names below.

Order in the UI:

1. **Direct (built-in)** — `direct_agent` when Kanaloa is the operator. Kanaloa runs the turn using the activated LLM (or the deterministic fallback when no profile is bound). *Chinese label: 内置直连.*
2. **Direct (external)** — `direct_agent` when an external agent is the operator. The platform is bridge, memory store, and monitor only. *Chinese label: 外部直连.*
3. **Coordinated execution** — `commander`. Kanaloa-only. Kanaloa plans and may delegate steps. *Chinese label: 统筹执行.*
4. **Tracked execution** — `pilot`. Kanaloa-only. Kanaloa records task lifecycle events while the user intervenes. *Chinese label: 追踪执行.*

External operators only show **Direct (external)** so you never see modes you cannot use.

---

## 3. Connecting OpenClaw (open-source AI agent)

- **Today's integration**: platform → API → **Local Bridge** → if `OPENCLAW_WEBHOOK_URL` is set, Bridge POSTs via **HTTP webhook** into your OpenClaw; otherwise Bridge emits a **handoff** file that you resolve manually and close the loop via callback (depending on task policy).
- **What you need**: a reachable Bridge (on this host or LAN), an OpenClaw-receiving URL (if using auto POST), and matching env vars between platform and Bridge (see root `.env.example` and the Bridge README).
- **Where to add it**: **`/agents/add`** → pick the OpenClaw template → fill **Agent ID**, adapter / registration info → submit.
- **Required fields**: at minimum a unique **Agent ID**; other fields follow the form's honest hints — the webhook depends on Bridge env, not on a single frontend string.
- **How to test**: after saving, open **`/agent-fleet/[id]`** → use **Test connection / Test run**; a successful call advances task status and shows an output summary; if it is stuck in waiting / handoff, follow the UI hints to inspect the webhook and callback.
- **What we claim in Beta**: registration, test runs, status observation. Webhook path is **automated** when the environment is fully wired.
- **Current limits**: without a configured webhook, we do **not** pretend we're fully automated. Multi-tenant isolation, production security, and SLAs are outside of Beta scope.

---

## 4. Connecting Cursor (closed-source AI agent)

- **Why not "full embedding"**: Cursor is a closed-source IDE and does **not** expose a stable public "remote headless task" API that would let this platform act as a true built-in.
- **Today's integration**: **Assisted** — Bridge emits a **handoff** (a readable file / instructions) + you run it inside Cursor + the task waits until **`POST /integrations/bridge/complete`** is called back.
- **What you need**: Cursor installed; ability to open whatever the handoff points to; completing the callback per the docs (or via a local helper script).
- **Where to configure**: add via **`/agents/add`**; inspect and PATCH at **`/agent-fleet/[id]`**.
- **What works**: unified registration, dispatch, status view, test run (which enters handoff / waiting), closing the loop on callback.
- **What doesn't**: there's no unattended, fully automated drive of Cursor UI; no guarantee of long-term vendor compatibility.

---

## 5. Connecting Claude Code (closed-source AI agent)

- **Today's integration**: also via **Local Bridge**. If the `claude` CLI is installed on the host, Bridge can try the **non-interactive CLI** path; otherwise we fall back to **handoff**, relying on a human or a later callback.
- **CLI / handoff / bridge**: **Bridge** is a small HTTP service on your machine; **CLI** means invoking the local `claude` command; **handoff** writes context into a file for you to continue in Claude Code; **callback** is how the outside world tells the platform the job is done.
- **How to configure**: **`/agents/add`** → pick the Claude Code template, fill ID, etc. Bridge / API URL / keys follow `.env.example`.
- **How to test**: the test area at **`/agent-fleet/[id]`**; watch whether you see a CLI success or a handoff / waiting state.
- **Current limits**: without the CLI we do **not** claim success. Vendor behavior is the source of truth.

---

## 6. Connecting a local script agent

- **Why it suits Embedded / Native**: the command runs on the **Bridge host**, so it doesn't depend on third-party closed-source IDE APIs. Path is short, repeatable, automation-friendly (but watch out for **command injection** and permissions — that's on you).
- **How to add**: **`/agents/add`** → pick a **local script / shell** template → configure `shell_command` and friends (the form is the source of truth).
- **How to test**: the details page has a test section; when it succeeds the run / task output shows a **stdout / stderr** summary (UI is the source of truth).
- **How you know success / failure**: task status (`succeeded` / `failed`), timeline events, and the test-run area text. On failure, we give you a **reason or suggestion** (handoff / policy block is also labelled).

---

## Related docs

- Capability matrix (engineer-facing): [`AGENT_INTEGRATION_MATRIX.md`](AGENT_INTEGRATION_MATRIX.md)
- Milestone progress and gaps: [`LOCAL_AGENT_CONTROL_PLANE_PROGRESS.md`](LOCAL_AGENT_CONTROL_PLANE_PROGRESS.md), [`LOCAL_AGENT_CONTROL_PLANE_GAP_LIST.md`](LOCAL_AGENT_CONTROL_PLANE_GAP_LIST.md)
- Verification and E2E evidence: [`FINAL_VALIDATION.md`](FINAL_VALIDATION.md)
