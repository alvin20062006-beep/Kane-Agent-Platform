# Kane-Kanaloa v3.0.1 (Beta)

Release tag: **v3.0.1-beta**. Early evaluation release: **known and unknown bugs
may exist**. This is not a production-readiness guarantee. Back up your data,
use disposable workspaces for testing, and review Agent side effects.

Kane is a thin, model-free **Conversation <-> Agent Harness**. It owns message
delivery, logical reply assembly, Turn routing, session continuity, Branch
history boundaries and persistence. Intelligence, tools, Subagents and execution
belong to the Agent, not Kane Core.

Kanaloa is the bundled first-party Agent using our modified DSH-based
**Kanaloa Harness**, not stock DSH. Upstream attribution and licenses are preserved.

```text
Kane Web UI -> Kane HTTP/SSE + Store -> Kanaloa / Kanaloa Harness
                                   -> Generic ConnectorAdapter
                                      <- Agent-side Connector <- External Agent
```

## Included

- Conversations, focus Turns, explicit parallel work, Branches and SSE.
- One logical reply becomes one Message, independent of streaming chunks.
- Cancel, permission forwarding, capability-dependent steering and recovery.
- Interrupted partial output and fail-closed recovery without blind reruns.
- Kanaloa Normal/Loop modes and in-page Base URL / Model / API Key configuration.
- External Agent registry, Connector pairing, Connect Skill, MCP bootstrap,
  shared conformance and the Codex reference Connector.

Availability does not prove model credentials or successful execution. An
Agent-side Connector must connect and remain running. Skill/MCP assist setup;
**MCP is not the persistent chat transport**.

## Windows Quick Start

Requirements: Node.js 24+, npm, Python 3.11+ and PowerShell. Tool-dependent work
requires the relevant shell/compute environment; IPython is not provided by
Kane Core. Pinned DSH packages 0.1.5-rc.3 are installed with Kane; a separate
stock DSH application is not required.

```powershell
git clone --branch v3.0.1-beta https://github.com/alvin20062006-beep/Kane-Agent-Platform.git
cd Kane-Agent-Platform
npm ci
npm run setup:api
npm run start:stack
```

Open http://127.0.0.1:3000. Web/API start together on ports 3000/8000.
Stop with `npm run stop:stack`. Legacy Local Bridge is optional, not the
unified Connector transport.

In Kanaloa settings, save your Provider's **Base URL, Model and API Key**, then
create a new conversation. No fixed model fallback is supplied. Settings apply
to new native sessions; existing sessions retain their selection. Keys use the
local Runtime credential store, not Kane's conversation database. Never commit
that store or paste keys into chat history.

SQLite defaults to `apps/api/kane.db`; `KANE_SQLITE_PATH` overrides it.
Runtime databases, credentials, logs and caches are excluded from Git.
[.env.example](.env.example) is historical guidance with placeholders, not a
complete vNext configuration contract. Set API process variables explicitly.
Do not expose the unauthenticated local default publicly; use
`OCTOPUS_API_TOKEN`, protected transport and deployment network controls.
When API token protection is enabled, the Web UI asks for that access token.
It is held in browser tab session storage and sent with API/SSE requests;
the Web proxy never substitutes its own server-side token for an anonymous caller.

## External Agents

1. Add an external Agent in Kane and obtain endpoint, identity and pairing code.
2. Give it [Connect Skill](skills/kane-connect/SKILL.md) and the
   [canonical Protocol](docs/KANE_CONNECTOR_PROTOCOL.md).
3. Configure its Agent-side Connector and transfer credentials through protected
   input, not source files or public issue reports.
4. Keep it running and use shared conformance checks.

[MCP bootstrap](connectors/kane-mcp/README.md) |
[Codex reference](connectors/codex/README.md) |
[Shared conformance](connectors/conformance/protocol.py).

Connector dependencies are installed separately. Kane does not install,
authenticate or guarantee support for every external Agent.

## Checks And Limitations

```powershell
npm run typecheck:web
npm run test:e2e:smoke
```

Smoke needs a running stack and Playwright Chromium
(`npx playwright install chromium` if absent). It is read-only, not model E2E.
Full suites were not rerun as a release gate; see [release notes](RELEASE_NOTES.md).

- Session/context rebind is not unfinished execution resume.
- Stop/cancel does not roll back external side effects.
- Approval depends on actual Agent/tool behavior.
- External compatibility, tools and Windows environment setup remain variable.
- Current UI model configuration centers on OpenAI-compatible APIs.
- The optional legacy Local Bridge still reports v2.0.0 and is not the vNext
  Connector transport. Historical v2 tags remain unchanged.

[CHANGELOG](CHANGELOG.md) | [RELEASE_NOTES](RELEASE_NOTES.md) |
[Third-party notices](THIRD_PARTY_NOTICES.md).

Existing project license status remains **UNLICENSED**. Third-party dependencies
retain their own licenses; this beta grants no new project-wide open-source license.
