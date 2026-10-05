# Kane-Kanaloa v3.0.1-beta

Date: 2026-10-05 (Australia/Sydney). Security/correctness patch on `main`.
**Known or unknown bugs may exist.** This is not production or universal Agent
compatibility certification. The earlier v3.0.0-beta and historical v2 tags remain.

## Patch Changes

- Fixed Web proxy privilege escalation when `OCTOPUS_API_TOKEN` is enabled:
  anonymous callers can no longer inherit the server token. The Web UI now
  accepts an explicit API access token in tab session storage for HTTP/SSE.
- Fixed external Connector permission projection that returned HTTP 500 when
  the UI requested a waiting Turn's details; rejected cross-Turn approval IDs.
- Upgraded Next.js to 16.3.8 and removed an unused vulnerable dev dependency.
  `npm audit --omit=dev` reports zero advisories at release time; dev-only
  lint/build dependencies retain advisory reports and should be revisited.
- API and Web version metadata now identify v3.0.1-beta. Optional legacy
  Local Bridge continues to report v2.0.0.

## Scope

Thin model-free Kane Harness, bundled Kanaloa/modified DSH Runtime, current
Web control UI, unified external Connector endpoint, generic Skill/MCP bootstrap,
shared conformance and Codex reference. Agent execution remains outside Kane Core.
No feature development or architecture refactor was performed during release preparation.

## Release Checks

- Web typecheck/build and full UI E2E: PASS, including anonymous/token proxy
  checks, conversation/approval/Loop/SSE and Connector pairing flows.
- API: 184 passed, 9 skipped (environment-dependent real Runtime tests).
- Bridge: 4 passed. MCP: 4 passed. Connector conformance: 7 passed.
- Web lint remains non-green on two pre-existing local pin-preference effects
  (`react-hooks/set-state-in-effect`); two image optimization warnings remain.
- Secret scan: no real secrets found in publishable files or new branch history.
  Test placeholders were reviewed.
- Git integrity: PASS. Dangling objects are not repository corruption.
- Runtime databases, credentials, local .env, logs, caches and account data
  are not uploaded. The tracked .env.example contains placeholders.
- Upstream DSH MIT notice preserved in THIRD_PARTY_NOTICES.md. Installed DSH
  packages retain LICENSE files; node_modules and virtual environments are excluded.

No fresh-machine, all-Agent or live model/crash acceptance was performed for
this patch. The E2E suite uses an isolated fixture Runtime, not the user's
saved Provider credentials.

## Earlier Evidence, Not A Fresh Release Retest

The 2026-10-01 acceptance recorded API 191 PASS / 0 SKIP, Bridge 4 PASS,
Web typecheck PASS, MCP 4 PASS, conformance 7 PASS and Codex reference regression
6 PASS. Real Kanaloa PONG, session continuity, two-cycle Loop, Tool success,
process-tree crash recovery and delayed completion after Cancel were exercised
using saved Provider configuration. These results do not guarantee another environment.

Approval was NOT_TRIGGERED, not fabricated as PASS. Subagent crash injection
terminated the shared Runtime process tree during child work; it was not an
isolated independent child-process crash test.

## Known Limitations / Untested Areas

- Session rebind is not unfinished work resume. Unknown outcomes stay interrupted;
  no blind rerun or side-effect rollback is promised.
- Continuable child recovery does not guarantee automatic resumed execution.
- Provider/network errors, permissions and Tool/IPython installation remain
  deployment-dependent.
- Pairing/registry presence is not a live compatible Agent-side Connector.
- UI model setup focuses on OpenAI-compatible Base URL/Model/API Key; not every
  Backend option has a UI control.
- All external Agents, fresh install, cross-machine reconnect, production
  deployment, load and adversarial security testing were not retested here.
- Some historical docs and the optional legacy Bridge still say v2.0.0.
- Never expose the default local unauthenticated service to the Internet.

## Data And Licensing

Breaking architecture baseline relative to v2. No automatic legacy data import
is promised. Back up databases and configuration before upgrading.
Historical releases are retained. Project license status remains UNLICENSED;
dependency attribution is in THIRD_PARTY_NOTICES.md.
