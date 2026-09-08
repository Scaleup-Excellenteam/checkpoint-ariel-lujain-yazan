# Check Point Chat

React UI → local FastAPI bridge → Python ChatClient → FastAPI server → PostgreSQL.
The bridge owns one ChatClient per browser connection; client.py isn't a separate process.

## Prerequisites

Python 3.12, Node 24 (or a version satisfying Vite's engine requirement), npm,
and PostgreSQL. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm --prefix client/ui ci
cp .env.example .env
```

Edit the ignored `.env` locally. Set `DATABASE_URL` to your PostgreSQL URL
(`postgresql://ROLE:URL_ENCODED_PASSWORD@localhost:5432/DATABASE`) and
`JWT_SECRET_KEY` to a private random value. Generate a value with:

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep the secret persistent between server restarts and quote values as shell
strings. Never put server secrets in Vite variables: those are public browser
configuration. JWT remains HS256 with a one-hour expiry and a string user ID
in `sub`. Replacing the old hardcoded secret invalidates previously issued
JWTs; users must log in again. Existing password hashes remain valid.

Provision the database and role with your PostgreSQL administrator. Then load
configuration into your shell and initialize the tables as the application
role (this is only needed because `psql` is a shell command):

```bash
set -a
source .env
set +a
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema.sql
```

The server does not create the database, role, or tables automatically. The
schema creates no rooms; the UI's Create Room action handles a fresh database.
The role needs table/sequence privileges. The Python server and bridge load
the repository-root `.env` themselves; no shell sourcing is needed to run them.
Configuration is read when each Python process starts, so restart the server or
bridge after changing a value that process uses.

## Run (three terminals)

Run each terminal from the repository root.

Terminal 1 — server:

```bash
source .venv/bin/activate
python -m uvicorn server.index:app --host 0.0.0.0 --port 8000
```

Terminal 2 — bridge and client:

```bash
source .venv/bin/activate
python -m uvicorn client.network.bridge:app --host 127.0.0.1 --port 9001
```

Terminal 3 — UI:

```bash
cd client/ui
npm run dev
```

Open http://127.0.0.1:5173 in two browser tabs. Vite uses strict port 5173;
stop the conflicting process if that port is occupied. The bridge endpoint
is `ws://127.0.0.1:9001/ws`; the upstream server endpoint is `/`.

For LAN use, start the server computer with the `0.0.0.0` command above and
allow incoming TCP port 8000 through its firewall. On each teammate's computer,
create a root `.env` containing only (at minimum) the server's reachable LAN
address, for example `CHAT_SERVER_URL=ws://192.168.1.20:8000/`; then run the
local bridge normally. The bridge reads that value automatically. The bridge
remains local to the browser, so leave `VITE_BRIDGE_URL` at
`ws://127.0.0.1:9001/ws`. Do not use `0.0.0.0` as a client destination and do
not copy `DATABASE_URL`, `JWT_SECRET_KEY`, or `VIRUSTOTAL_API_KEY` to client
computers.

`CHAT_SERVER_URL` defaults to localhost when omitted. `CHAT_UI_ORIGINS` can
override the bridge's comma-separated exact Origin allowlist; defaults allow
localhost/127.0.0.1 on ports 5173 and 5500. Other origins are rejected.
For a different bridge address or mock mode, copy `client/ui/.env.example` to
`client/ui/.env.local` and edit `VITE_BRIDGE_URL` or `VITE_USE_MOCKS`. Restart
Vite after configuration changes. Mock mode does not test shared messaging
or PostgreSQL.

See [TESTING.md](TESTING.md) for automated and manual verification and
[docs/protocol.md](docs/protocol.md) for the browser JSON contract.
