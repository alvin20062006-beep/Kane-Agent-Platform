<p align="center"><img src="apps/web/public/kane-octopus.png" width="112" alt="Kane Agent Platform logo"></p>
<h1 align="center">Kane Agent Platform</h1>
<p align="center"><strong>One workspace. Your Agents. Work that keeps moving.</strong></p>
<p align="center">A local-first workspace for ongoing AI conversations and parallel Agent tasks.</p>
<p align="center">
  <a href="#status"><img src="https://img.shields.io/badge/status-beta-orange" alt="Beta"></a>
  <img src="https://img.shields.io/badge/Node.js-24%2B-339933" alt="Node.js 24 or newer">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm_Noncommercial-blue" alt="PolyForm Noncommercial"></a>
</p>
<p align="center"><a href="https://alvin20062006-beep.github.io/Kane-Agent-Platform/">Website</a> · <a href="#why-kane-agent-platform">Why Kane</a> · <a href="#quick-start">Get started</a> · <a href="https://github.com/alvin20062006-beep/Kane-Agent-Platform/issues">Feedback</a></p>

Keep a conversation going while your Agent works. Start another task, explore a branch, review an approval, and return to the work that needs your attention.

**Kane Agent Platform brings those interactions into one local interface.** It includes Kanaloa as its built-in Agent and supports external Agents through compatible Connectors. Model access, credentials and execution capabilities depend on the Agent you configure.

> **Beta software.** Use disposable workspaces for evaluation and review Agent actions. Model credentials and usage credits are not included; this release does not guarantee production readiness.

## Why Kane Agent Platform

| When you want to… | Use… |
| --- | --- |
| Continue an ongoing task | Persistent conversation history and native-session connections |
| Work on several things | Parallel tasks with an explicit focused task |
| Try a different direction | Branches from earlier messages |
| Adjust a running task | Follow-up instructions or steering supported by the Agent |
| Decide what happens next | Approvals, cancellation and optional Loop mode |
| Bring another Agent | A compatible Agent-side Connector and pairing |

The web interface supports Chinese and English. Optional Python tools retain variables within a live session and require a separately built Docker image.

## Quick start

Use **Node.js 24+**, npm and **Python 3.11+** with pip and venv. On Linux, install your distribution's `python3-venv` package if needed.

From a Linux terminal:

```sh
git clone https://github.com/alvin20062006-beep/Kane-Agent-Platform.git
cd Kane-Agent-Platform
npm ci
python3 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -r apps/api/requirements.txt
npm run dev:stack
```

Open [**http://127.0.0.1:3000**](http://127.0.0.1:3000). The development launcher starts the API and web interface together; press **Ctrl+C** to stop them.

On Windows, use PowerShell after cloning and running `npm ci`:

```powershell
npm run setup:api
npm run dev:stack
```

The optional Local Bridge is separate from the external-Agent Connector transport. It is not required for this quick start.

### Connect your model

1. Open Kanaloa settings.
2. Enter your provider's **Base URL**, **Model** and **API Key**, then save.
3. Create a new conversation and send a message.

Use a service compatible with a format supported by the settings screen. New model settings apply to new native sessions. Model requests go to your configured provider and may incur charges.

### Optional Python tools

With a Docker Linux engine running:

```sh
npm run setup:kanaloa-tools
```

Windows requires Docker Desktop's Linux-container mode. See [Python tools](packages/kanaloa-tools/README.md) for setup and authorization requirements. Live Python state is not a durable checkpoint and does not survive worker loss or restart.

### External Agents

Pair an Agent in the interface, then run its compatible Connector on the Agent host. Keep that process running for communication.

- [Codex Connector](connectors/codex/README.md)
- [MCP setup helper](connectors/kane-mcp/README.md)
- [Connector protocol](docs/KANE_CONNECTOR_PROTOCOL.md)

MCP helps with setup and discovery. Continuous Agent communication uses the Connector. Support for every Agent is not implied.

## Your data and control

Conversation data is stored locally in SQLite, by default at `apps/api/kane.db`. Set `KANE_SQLITE_PATH` to choose another location. Credentials belong in the runtime's protected local credential store, never in source or chat history.

Keep services on localhost. If remote access is needed, configure API authentication, encrypted transport and network access controls. The API supports `OCTOPUS_API_TOKEN`; the web interface asks for the access token when protection is enabled.

Cancellation does not undo completed file changes or external actions. Reconnecting a session does not guarantee interrupted execution can resume. Agent capabilities determine available behavior.

## Status

Current source version: **3.0.1-beta**. The website is an introduction; run the project locally to use the workbench. This README does not certify every provider, operating system or optional tool configuration.

Found an issue? Include the version, environment and reproduction steps in [Issues](https://github.com/alvin20062006-beep/Kane-Agent-Platform/issues). Keep API keys, private conversations and local databases out of public reports. If the project is useful to you, a Star helps others discover it.

## License

[PolyForm Noncommercial 1.0.0](LICENSE). Source access does not grant unrestricted commercial use; commercial use requires separate permission. Third-party components retain their own licenses; see [Third-party notices](THIRD_PARTY_NOTICES.md).
