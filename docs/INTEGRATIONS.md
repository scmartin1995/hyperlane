# Integrations: Slack, Microsoft Teams, email intake

Hyperlane is local-first. **Nothing is sent anywhere unless you set the matching variables in `.env`.**
Secrets (tokens, passwords, webhook URLs) live only in `.env`; they are never written to the database.
Every outbound message is recorded in the notification log (`GET /api/notifications/log`, also shown in
Settings → Integrations), including failures.

| Integration | Direction | Needs a public URL? | Env vars |
|---|---|---|---|
| Slack (Socket Mode) | in + out | **No** (outbound websocket) | `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_DEFAULT_CHANNEL` |
| Microsoft Teams (incoming webhook) | out only | No | `TEAMS_WEBHOOK_URL` (per-project override in project settings) |
| Email intake (IMAP + SMTP) | in + out | No | `INTAKE_IMAP_*`, `INTAKE_SMTP_*`, `INTAKE_FROM_ADDRESS`, `INTAKE_POLL_SECONDS` |

Check everything from the UI (Settings → Integrations → *Test*) or with
`POST /api/integrations/test/slack|teams|email`. Restart Hyperlane after changing `.env`.

---

## 1. Slack

Socket Mode means the bot opens an outbound websocket to Slack; your machine never has to accept
inbound connections, so this works on a laptop behind NAT.

### Create the app
1. Go to <https://api.slack.com/apps> → **Create New App** → **From scratch**. Name it `Hyperlane`,
   pick your workspace.
2. **Socket Mode** (left menu) → toggle **Enable Socket Mode**. It asks you to create an
   *app-level token*: name it `hyperlane-socket`, scope `connections:write`, **Generate**.
   Copy the `xapp-…` token → `SLACK_APP_TOKEN`.
3. **OAuth & Permissions** → *Bot Token Scopes* → add:
   - `chat:write` (post messages), `chat:write.public` (post to channels the bot wasn't invited to)
   - `channels:history`, `groups:history`, `im:history` (read thread replies on item messages)
   - `app_mentions:read` (answer `@Hyperlane …`)
   - `commands` (slash command)
   - `users:read`, `users:read.email` (map Slack users to Hyperlane profiles by email)
   - `im:write` (open DMs for assignment pings and the private daily digest)
4. **Event Subscriptions** → **Enable Events** (no Request URL is needed in Socket Mode) →
   *Subscribe to bot events* → add `message.channels`, `message.groups`, `message.im`, `app_mention`.
   **Save Changes**.
5. **Slash Commands** → **Create New Command**: command `/hyperlane`, short description
   `Hyperlane: mine, HL-12 done, todo, ask, standup`, usage hint `mine | HL-12 done | todo <text> | ask <q> | standup`.
   (Request URL can be anything, it is not used in Socket Mode.) Save.
6. **App Home** → enable *Messages Tab* and *Allow users to send Slash commands and messages from the messages tab*
   (lets people DM the bot).
7. **Install App** → **Install to Workspace** → allow. Copy the **Bot User OAuth Token** `xoxb-…` →
   `SLACK_BOT_TOKEN`.
8. In Slack, invite the bot to the channel(s) you want updates in: `/invite @Hyperlane` in `#project-updates`.

### Configure Hyperlane
```env
SLACK_BOT_TOKEN=xoxb-…
SLACK_APP_TOKEN=xapp-…
SLACK_DEFAULT_CHANNEL=#project-updates      # fallback; each project can set its own `slack_channel`
```
Restart. The log should say `slack socket mode handler started`; **Test** should report `auth.test ok as hyperlane in <team>`.

### Link people
Each person sets **People → their profile → Slack user id** (`U0…`, from Slack profile → *Copy member ID*),
*or* simply uses the same email in Hyperlane and Slack: the first time an unknown Slack user talks to the bot,
Hyperlane calls `users.info`, matches the email and stores the id. Unlinked users get an ephemeral
"Link your profile in Hyperlane → People" reply.

Per-user preferences (People → profile → *Preferences*):
- `slack_dm: true` — allow DMs (daily digest at 09:00, assignment pings)
- `notify_assignments: true` — DM me when I get assigned an item (needs `slack_dm` too)

### What the bot does
Outbound (to the project's channel, or `SLACK_DEFAULT_CHANNEL`):
- Item status / assignee / blocked changes → one message per item, with a card the first time, then **threaded replies**
  under that card for every later change and web comment.
- Sprint started / closed → summary (goal, committed, completed, carried over).
- Daily digest 09:00 local → yesterday's done, today's in progress, blocked.
- DMs (opt-in): assignment pings; daily digest with *your* in-progress items, overdue due dates and the **count**
  of overdue private action items (never their contents).

Inbound:
- Reply in an item's thread → becomes a comment on the item (`source=slack`), attributed to your linked profile.
- `@Hyperlane what's blocking HL-12?` → the BA agent answers in the thread.
- `/hyperlane …` slash command:

| Command | Does |
|---|---|
| `/hyperlane mine` | your open items grouped by status (ephemeral) |
| `/hyperlane HL-12 done` / `start` / `review` / `<status key or name>` | moves the item; replies with the updated card |
| `/hyperlane HL-12` | show the item card |
| `/hyperlane todo Call the vendor` | private action item for you (ephemeral confirmation) |
| `/hyperlane ask Which items are at risk this sprint?` | BA agent quick answer (ephemeral) |
| `/hyperlane standup` | posts *your* yesterday / today / blockers to the channel |
| `/hyperlane help` | the list above |

### What leaves the machine (Slack)
Item keys, titles, status names, assignee names, change summaries, comment text (web comments mirrored to
threads), sprint goals and numbers, digest lists, agent answers to `ask`/mentions (the question is also sent
to your configured Claude provider), and a link `http://<HYPERLANE_HOST>:<PORT>/items/<id>` that only works
on your LAN. Private action items: **counts only**, never titles or notes. Nothing about projects without a
channel is posted unless `SLACK_DEFAULT_CHANNEL` is set.

---

## 2. Microsoft Teams (incoming webhook)

Outbound only: Hyperlane POSTs cards to a webhook URL. Teams can't talk back.

1. In Teams, open the channel → **⋯** → **Manage channel** (or **Connectors** on older tenants) →
   **Workflows** → *Post to a channel when a webhook request is received* → **Add workflow**, name it `Hyperlane`,
   choose the team/channel → **Add workflow** → copy the URL.
   (Classic *Incoming Webhook* connectors also work; Hyperlane sends an Adaptive Card and falls back to the
   legacy MessageCard format automatically if the endpoint rejects it.)
2. `.env`:
   ```env
   TEAMS_WEBHOOK_URL=https://prod-….logic.azure.com/…
   ```
3. A project can use a different channel: Project settings → *Teams webhook override*.
4. Restart, then **Test** (posts a "Hyperlane test card").

Sends the same events as Slack (item updates, comments, sprint summaries, daily digest) as cards with a
title, text and a facts table. No DMs, no inbound.

### What leaves the machine (Teams)
Same item/sprint/comment data as Slack. The webhook URL itself contains a secret: it is kept in `.env`
only and logged redacted (host only).

---

## 3. Email intake (IMAP poll + SMTP replies)

Hyperlane watches one mailbox. Every **unseen** mail becomes an intake request; the BA agent summarises it,
asks at most `max_questions` clarifying questions by replying in the same thread, and then proposes backlog
items you can convert. Replies from the requester are matched by `In-Reply-To` / `References` and attached to
the request.

Use a **dedicated mailbox** (e.g. `requests@yourteam.com`), never your personal inbox: everything unseen in it
will be ingested and marked read.

### Gmail / Google Workspace example
1. Create (or pick) the mailbox, e.g. `hyperlane-requests@gmail.com`.
2. Turn on 2-step verification for that Google account, then create an **App password**
   (Google Account → Security → *2-Step Verification* → *App passwords* → app "Mail", device "Hyperlane").
   You get a 16-character password.
3. Gmail → Settings → *Forwarding and POP/IMAP* → **Enable IMAP**.
4. `.env`:
   ```env
   INTAKE_IMAP_HOST=imap.gmail.com
   INTAKE_IMAP_USER=hyperlane-requests@gmail.com
   INTAKE_IMAP_PASSWORD=abcd efgh ijkl mnop        # the app password (spaces are fine)
   INTAKE_IMAP_FOLDER=INBOX
   INTAKE_SMTP_HOST=smtp.gmail.com
   INTAKE_SMTP_PORT=587
   INTAKE_SMTP_USER=hyperlane-requests@gmail.com
   INTAKE_SMTP_PASSWORD=abcd efgh ijkl mnop
   INTAKE_FROM_ADDRESS=hyperlane-requests@gmail.com
   INTAKE_POLL_SECONDS=60
   ```
   Any IMAP/SMTP provider works (Fastmail, Office 365 with an app password, your own Dovecot/Postfix):
   IMAP is always over SSL (port 993); SMTP uses STARTTLS on the port you give.
5. Restart, then **Test** (logs in to IMAP and reports the message count; says whether SMTP is configured).

Behaviour:
- Poll every `INTAKE_POLL_SECONDS` (minimum 15 s) for `UNSEEN` mails in the folder; each is parsed
  (subject, sender, text body — HTML is stripped when there is no plain-text part), deduplicated by
  `Message-ID`, turned into an intake request (or attached to an existing one when it is a reply), then
  marked `\Seen`. Mails that fail to ingest stay unread and are retried.
- Replies are sent **only** as answers to an intake request (the agent's clarifying question, or a message you
  send from the intake screen), threaded with `In-Reply-To`/`References`, from `INTAKE_FROM_ADDRESS`.
  Set only the IMAP variables if you want to read but never reply.

### What leaves the machine (email)
Only the reply text you (or the agent) send to the requester's address. The incoming mail body is also
sent to your configured Claude provider for analysis, like any other intake request. Mailbox credentials
stay in `.env`.

---

## Notification log & manual sends
- `GET /api/notifications/log?limit=50` — the last sends across all channels (`ok`, `error`, target, kind).
- `POST /api/notifications/send {"channel": "slack"|"teams", "target"?: "#channel"|webhook, "text": "…"}` —
  send an ad-hoc message as yourself (also used by the agent's *send Slack message* tool, only on explicit ask).
- Every send emits a `notification.sent` event on the live stream.
