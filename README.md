# 🏁 Hyperlane

**Local-first, agentic project management.** Kanban, hierarchical backlog (epics → features → stories),
sprints with learned capacity, retros, agile telemetry and earned-value management, private action
items, Slack/Teams updates, email intake with an agent that asks the follow-up questions, and a
business-analyst chat that can build your backlog from a conversation.

Everything runs on one machine. Data lives in a single SQLite file. The only things that ever leave
the box are prompts to Claude through the provider you choose (Anthropic API, Amazon Bedrock, or
your Claude Code subscription) and the messages you explicitly route to Slack, Teams or email.

> Plan, build and ship with an AI analyst on the team.

## Quick start

```bash
git clone <this repo> hyperlane && cd hyperlane
./hyperlane            # installs (uv + npm), builds the UI, starts http://127.0.0.1:8787
```

Requirements: [uv](https://docs.astral.sh/uv/) and Node 20+. First run opens the **Welcome to the League**
wizard: name the workspace, create your profile, pick a project template, seed the backlog (agent prompt,
Excel/CSV import, or the demo league), and connect integrations.

Other commands:

| Command | What it does |
|---|---|
| `./hyperlane --dev` | API with autoreload on :8787 + Vite dev server on :5173 |
| `./hyperlane --build` | rebuild the UI |
| `./hyperlane --seed` | load the demo league |
| `uv run pytest` | run the backend tests |

To let teammates use it, bind to your LAN: set `HYPERLANE_HOST=0.0.0.0` in `.env` and share
`http://<your-ip>:8787`. Profiles are picked from a list (optional PIN per profile protects private
action items). There is no cloud, no telemetry, no CDN at runtime.

## Configure Claude

Edit `.env` (created on first run from `.env.example`) and pick **one** provider:

| `HYPERLANE_LLM_PROVIDER` | What you need |
|---|---|
| `claude-code` (default) | Claude Code installed and logged in on this machine (`claude` CLI). Uses your subscription. |
| `anthropic` | `ANTHROPIC_API_KEY=sk-ant-…` (or an `ant auth login` profile) |
| `bedrock` | AWS credentials + `AWS_REGION`, optional `HYPERLANE_BEDROCK_MODEL` |

The agent works without any provider too (you just lose the chat, intake clarification and the
smart parts of import/planning). Slack, Teams and email intake are documented in
[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md).

## What's inside

- **Assistant** – an ask bar on every page. Chat with a business analyst that reads and changes the backlog,
  summarizes sprints, reviews a plan, drafts stories, and creates your tasks. Streams its tool calls live.
- **Board** – drag-and-drop kanban with WIP limits, swimlanes, filters, quick-add.
- **Backlog** – epic → feature → story tree, drag to rank or re-parent, bulk actions, sprint drop targets.
- **Sprints** – guided planning flow (capacity → pick → commit) using learned per-person capacity,
  burndown, close with carry-over, retro board with an assistant summary that turns actions into private tasks.
- **Insights** – velocity, cumulative flow, cycle-time scatter, throughput, Monte Carlo forecast,
  and full EVM (PV/EV/AC, SPI/CPI, EAC/ETC/VAC/TCPI, S-curve, daily snapshots).
- **Inbox** – requests arrive by email or form; the assistant extracts requirements, asks up to N
  focused questions, then proposes backlog items you can convert in one click.
- **My tasks** – private per-person to-dos with notes, due dates, snooze; fed by retros,
  Slack `/hyperlane todo …`, and the assistant.
- **Team** – profiles, skills, capacity defaults, learned capacity and insights.
- **Settings** – project types, workflow and item-type editors, EVM config, integrations, import.

Look & feel: warm cream surfaces with bold purple, rust, teal and gold color-blocked cards (a dark theme is one click away).

## Project templates

Software · Scrum, Software · Kanban, Product discovery, Marketing campaign, Hardware product,
Operations / IT, and Blank. Each sets item types, workflow states, WIP limits, estimation mode
(points / hours / throughput) and sprint length; all editable afterwards.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/API.md](docs/API.md). FastAPI + SQLAlchemy + SQLite on the
back; Vite + React + Tailwind on the front, served by the same process. Live updates via SSE.

## Security & privacy

See [docs/SECURITY.md](docs/SECURITY.md) for exactly what data moves where.
