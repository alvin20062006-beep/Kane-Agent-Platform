# Product & deployment notes

This page summarizes important **Kāne / Kane Agent Platform** boundaries for self-hosted setups (for operators and integrators—not a full legal notice).

## Capability boundaries (summary)

- **Local-first**: default file-backed persistence; optional PostgreSQL with a compatibility-oriented schema that may evolve.
- **Identity & credentials**: manage API keys and Bridge secrets in your environment; never commit `.env` to version control.
- **External agents**: Bridge, webhooks, CLI / handoff paths depend on your OS processes and network—the platform does not replace your security review.

## Before production-style exposure

For multi-tenant or internet-facing deployments, add your own authentication, audit, backup, and key management. See `docs/DEPLOYMENT_*.md` and `docs/ARCHITECTURE.md` when shipped with your distribution.
