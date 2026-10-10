# Data flow & security

Hyperlane is designed so a team can run it on one laptop or a small box on the LAN without any
third-party service holding the data.

## Where data lives
- `data/hyperlane.db` — the only datastore (SQLite, WAL mode). Back it up by copying the file.
- `data/uploads/` — Excel/CSV files you import (delete anytime).
- `data/agent-cwd/` — empty scratch dir handed to the Claude Code provider as its working directory.
- `.env` — all secrets (API keys, Slack tokens, mailbox password). Never written to the DB, never committed.

## What leaves the machine, and only when you configure it
| Flow | Sent | To | Trigger |
|---|---|---|---|
| Agent chat / intake / backlog builder / import mapping / retro summary | the prompt + the project context the agent needs (item titles/descriptions, sprint numbers, people names) | Anthropic API, Amazon Bedrock in **your** AWS account, or Claude Code (your subscription) | you ask the agent, or an intake email arrives |
| Slack notifications & slash commands | item key/title/status, comments, sprint summaries, digests | your Slack workspace (Socket Mode: outbound websocket, no inbound port) | item changes, `/hyperlane …` |
| Teams | same as Slack, outbound only | your Teams webhook | item/sprint changes |
| Email intake | clarifying questions / confirmations | the requester, via your SMTP | new request or reply |

Private action items and their notes are **never** included in Slack/Teams messages (digests only send counts
to the owner's DM) and are only returned to the owner's session.

## Identity
Profiles are picked from a list; an optional PIN (bcrypt-hashed) can be set per profile. The session is a
signed cookie (`HYPERLANE_SECRET`). This is deliberately lightweight: Hyperlane is meant for a trusted team on
a private network. Do not expose port 8787 to the internet.

## Hardening checklist
- Set a long random `HYPERLANE_SECRET` (the launcher does this on first run).
- Bind to `127.0.0.1` (default) or your LAN interface only.
- Put PINs on profiles if the machine is shared.
- Back up `data/` regularly; it's just files.
- If you use Bedrock, use a least-privilege IAM role with `bedrock:InvokeModel*` only.
