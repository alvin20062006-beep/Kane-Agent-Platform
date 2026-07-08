# Verify Kane v2.0.0

This guide verifies a local Kane Agent Platform checkout using the scripts that ship with v2.0.0. It does not require hosted services. Local LLM replies only work when you configure a model profile or process-level provider key.

## Baseline Checks

Run from the repository root:

```bash
npm run typecheck:web
npm run test:api
npm run test:bridge
```

Recommended first-time setup:

```bash
npm install
npm run setup
```

`npm run setup` creates the API and Local Bridge Python environments. If you skip it, the scripts may fall back to system Python and print a setup hint.

`npm install` installs the root JavaScript dev dependencies used by verification scripts, including Playwright for `npm run test:e2e:smoke`.

## Start The Local Stack

```bash
npm run dev:stack
```

This starts:

```text
Web:    http://127.0.0.1:3000
API:    http://127.0.0.1:8000
Bridge: http://127.0.0.1:8010
```

In another terminal:

```bash
npm run wait:stack
npm run test:e2e:smoke
```

`wait:stack` fails if the stack is not reachable. `test:e2e:smoke` uses the real Web/API/Bridge stack and checks the core pages for request failures and severe browser errors.

## Health And Diagnostics

Lightweight health:

```text
GET http://127.0.0.1:8000/health
GET http://127.0.0.1:8010/health
```

Heavier diagnostics:

```text
GET http://127.0.0.1:8000/health/diagnostics
GET http://127.0.0.1:8000/metrics
GET http://127.0.0.1:8000/watchdog
GET http://127.0.0.1:8010/v1/status
```

Diagnostics and metrics may use short-lived cached probes to avoid duplicate Bridge load under concurrency. They must not hide offline or failed Bridge state.

## Human E2E Checklist

Use a real browser against `http://127.0.0.1:3000`.

1. Open Dashboard.
2. Open Conversations.
3. Confirm the no-model state is clear when no LLM profile/key is active.
4. Open Settings and verify platform status loads or shows a clear fallback.
5. Open Tasks.
6. Create a low-risk builtin task.
7. Open Task Detail.
8. Inspect Execution Audit.
9. Inspect Run Timeline.
10. Confirm task, run, and run steps converge to terminal state.
11. Open Agent Fleet.
12. Open Codex agent detail and confirm real adapter status.
13. Run a low-risk Codex task only if the local CLI is available; permission errors must be recorded honestly.
14. Open Cursor agent detail and confirm handoff-oriented behavior.
15. Open Memory and inspect ledger/snapshot/retrieval audit panels.
16. Open Local Bridge.
17. Return to Dashboard.

Do not treat missing local model keys, unavailable CLIs, or OS permission failures as fake successes. Record them as expected environment behavior or real failures.

## Stop The Stack

```bash
npm run stop:stack
```

The stop script only stops processes that are manifest-owned or verified as this repo's dev stack. It reports unknown listeners instead of force-killing them.

Final stop success requires:

```text
3000 DOWN
8000 DOWN
8010 DOWN
8011 DOWN
HTTP probes fail for all four ports
```

See [SAFE_STOP_AND_RESTORE.md](SAFE_STOP_AND_RESTORE.md) before restoring local runtime data.

## Fresh Clone Verification

For public release readiness, verify from a clean checkout:

```bash
git clone <repo-url> kane-v2-fresh
cd kane-v2-fresh
npm install
npm run setup
npm run typecheck:web
npm run test:api
npm run test:bridge
npm run dev:stack
npm run wait:stack
npm run test:e2e:smoke
npm run stop:stack
```

A fresh clone must not depend on `.runtime-logs`, `.next`, pytest cache, runtime JSON data, handoff files, or local archive directories.
