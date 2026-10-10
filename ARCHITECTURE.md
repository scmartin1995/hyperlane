# Hyperlane architecture & conventions

Local-first, single-process project management server with an embedded Claude agent.
Nothing leaves the machine except: (1) prompts to Claude via the provider you configure
(Anthropic API, Amazon Bedrock, or your Claude Code subscription), (2) messages you explicitly route to
Slack/Teams/email. Data is one SQLite file in `./data/`.

```
hyperlane/
  hyperlane                 # launcher script: installs, builds, runs  (./hyperlane | ./hyperlane --dev)
  pyproject.toml            # python package "hyperlane" (backend/hyperlane), console script `hyperlane`
  backend/hyperlane/
    main.py                 # FastAPI app factory; serves frontend/dist; lifespan starts scheduler + integrations
    config.py               # Settings from .env (secrets never in DB)
    db.py                   # SQLAlchemy engine/session (sqlite WAL), get_db dep, session_scope()
    models/                 # ORM (core, planning, personal, intake, chat, evm, integrations)
    schemas/common.py       # pydantic out-models shared across routers
    api/                    # routers, auto-discovered (module-level `router`)
    services/               # business logic (templates, events bus, auth, scheduler, bootstrap, + domain services)
    agent/                  # Claude provider abstraction, tool registry, BA chat, intake, backlog builder, importer
    integrations/           # slack (socket mode), teams (webhook), email (imap/smtp), notification router
  frontend/ (Vite + React 19 + TS + Tailwind v4 + TanStack Query + dnd-kit + Recharts)
    src/api/{client,types,queries}.ts   # fetch wrapper, shared types (contract), base hooks
    src/components/ui       # UI kit (Button, Panel, Badge, Avatar, Input/Select/Textarea/Field/Toggle, Progress, Stat,
                            #   Tabs, Modal, Drawer, Menu, EmptyState, Skeleton, Spinner, PageHeader, toast/Toaster, celebrate(), Markdown)
    src/components/layout   # AppShell (sidebar/topbar/agent drawer/command palette)
    src/features/<area>/    # one folder per page; default-export page component; feature-local hooks in hooks.ts
    src/lib/{store,format,live}.ts      # zustand UI store + flavor labels, formatting helpers, SSE sync
    src/styles/{tokens,global}.css      # design tokens (dark/light) + tailwind theme + HUD utilities
docs/API.md                 # the API contract — read it before writing any endpoint or hook
```

## Conventions
- **Python**: 3.12+, type hints, SQLAlchemy 2.0 style (`Mapped`, `select()`), pydantic v2. Routers thin; logic in `services/`.
  Emit `bus.emit(...)` after commits. Log `Activity` rows via `services/activity.py::record(db, ...)` (backend-core writes it; others import it).
- **Frontend**: functional components, TanStack Query for all server state (`qk` keys in `api/queries.ts`), zustand only for UI state.
  Use the UI kit; don't invent new primitives when one exists. Tailwind utility classes with the theme colors
  (`bg-surface`, `text-text-2`, `text-gold`, `border-border`, …). Page container is provided by AppShell (padding, max width).
  Keyboard-first: every list has a shortcut; every form submits on Enter/Ctrl+Enter.
- **Look & feel**: dark HUD by default (tokens in `styles/tokens.css`). Display font Titillium Web (uppercase, tracked), body Overpass,
  numbers in JetBrains Mono (`.num`). Gold = primary accent, teal = interactive/in-progress, rust = danger, purple = epics, green = done.
  Panels: `.panel` (+ `.panel-cut` for the angled HUD corners), `.hairline`, `.eyebrow`, `.grid-bg`, `.animate-in/pop`.
  Copy is punchy and a little playful ("No prophecy. Just skill, strategy, and the will to ship."), but every flavored label has a plain
  subtitle (see `LABELS` in `lib/store.ts`; `useUI().flavor` toggles). Fun moments: `celebrate()` confetti on done/sprint close,
  `toast.fun()` for wins. Never block the user with flavor.
- **Privacy**: action items + notes are only ever returned for `CurrentUser`. No analytics, no CDNs at runtime (fonts are bundled).
- **Events**: see docs/API.md → Events. The UI refetches via SSE; don't build polling.
- **Tests**: `uv run pytest` – use `fastapi.testclient.TestClient(app)` with `HYPERLANE_DB_PATH` pointed at a temp file (see tests/conftest.py).

## Module ownership (parallel build)
| Area | Owner | Files |
|---|---|---|
| core CRUD, activity, seed, search | backend-core | api/{users,projects,items,sprints,action_items,search,dev}.py, services/{items,sprints,activity,projects,users,ranking,seed}.py, tests/test_core.py |
| metrics/EVM/forecast/capacity/retro | backend-analytics | services/{metrics,evm,forecast,capacity,retro}.py, api/{reports,planning}.py, tests/test_analytics.py |
| Claude provider, BA chat, intake, backlog builder, excel import | backend-agent | agent/*, api/{chat,intake,imports}.py, tests/test_agent.py |
| Slack/Teams/email/router | backend-integrations | integrations/*, api/integrations.py, tests/test_integrations.py |
| welcome, home, board, backlog, item detail | frontend-a | features/{welcome,home,board,backlog,items}/* |
| sprints/planning/retro, reports, people, action items, intake, chat, settings/import | frontend-b | features/{sprints,reports,people,action-items,intake,chat,settings}/* |
Shared files (`schemas/common.py`, `api/types.ts`, `components/ui/*`, `AppShell.tsx`, `live.ts`) may be **extended** (append) but not restructured.
