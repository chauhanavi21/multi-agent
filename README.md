# Phase 1 — Local Sales Agent (single-agent vertical slice)

A working sales agent that finds leads, drafts personalized cold emails, and logs follow-ups. Runs 100% locally — no API costs.

## Architecture

```
React (Vite)  ──HTTP/SSE──▶  FastAPI  ──▶  LangGraph agent  ──▶  Ollama (local LLM)
                                │
                                └──▶  PostgreSQL (leads, emails, runs)
```

## Prerequisites — install these first

| Tool | Version | Link |
|------|---------|------|
| Python | 3.11+ | https://www.python.org/downloads/ |
| Node.js | 20+ | https://nodejs.org/en/download |
| Docker Desktop | latest | https://www.docker.com/products/docker-desktop/ |
| Ollama | latest | https://ollama.com/download |
| Git | latest | https://git-scm.com/downloads |

Verify each:
```bash
python --version    # 3.11.x or higher
node --version      # v20.x or higher
docker --version    # any recent
ollama --version    # any recent
```

## Step 1 — Pull the LLM models

```bash
ollama pull llama3.1:8b        # main reasoning model (~4.7GB)
ollama pull qwen2.5:7b         # backup, better at structured output (~4.4GB)
```

Test it works:
```bash
ollama run llama3.1:8b "write a one-line sales pitch for a CRM"
```

Keep Ollama running in the background — it serves at `http://localhost:11434`.

## Step 2 — Start PostgreSQL via Docker

From the project root:
```bash
docker compose up -d
```

This starts Postgres on port 5432 with database `salesagent`, user `agent`, password `agentpass`. Data persists in a Docker volume.

Verify:
```bash
docker compose ps    # should show postgres "running"
```

## Step 3 — Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m app.db.init_db          # creates tables + seeds 5 demo leads
uvicorn app.main:app --reload --port 8000
```

Backend now running at http://localhost:8000. API docs at http://localhost:8000/docs.

## Step 4 — Frontend setup

In a new terminal:
```bash
cd frontend
npm install
npm run dev
```

Frontend at http://localhost:5173.

## Usage

1. Open http://localhost:5173
2. You'll see 5 seeded leads
3. Click "Draft email" on any lead → watch the agent stream its reasoning + final email
4. Edit the email if you want, click "Send" → logs the outreach with status `sent` (no real email goes out — uses a mock sender)
5. Click "Find more leads" → agent generates 3 new fictional leads matching a criteria you provide

## Project structure

```
phase1/
├── docker-compose.yml         # Postgres
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # FastAPI app, routes, SSE streaming
│       ├── config.py          # env vars
│       ├── db/
│       │   ├── models.py      # SQLAlchemy: Lead, EmailDraft, AgentRun
│       │   └── init_db.py     # create tables + seed
│       ├── agents/
│       │   └── sales_agent.py # LangGraph state machine
│       └── tools/
│           ├── lead_tools.py  # search_leads, generate_leads
│           ├── email_tools.py # draft_email, send_email (mocked)
│           └── crm_tools.py   # log_followup
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api/client.js
        └── components/
            ├── LeadList.jsx
            ├── AgentStream.jsx
            └── EmailEditor.jsx
```

## What's wired up vs faked

- **Real**: agent loop, tool calls, LLM via Ollama, DB persistence, SSE streaming, React UI
- **Faked (intentionally — wire real later)**: email sending logs to DB only, lead "search" is mocked since web scraping needs real credentials

## Phase 2 preview

This codebase is built so Phase 2 (manager + dev agents + analyst) drops in cleanly:
- `agents/` folder takes new agent modules
- The LangGraph supervisor pattern is one node away from being added
- The `AgentRun` model already tracks `parent_run_id` for multi-agent traces

## Troubleshooting

- **Ollama connection refused**: ensure `ollama serve` is running (Docker Desktop user? Ollama installs as a service on macOS/Windows and starts automatically. On Linux: `systemctl start ollama`)
- **Postgres connection refused**: check `docker compose ps` and `docker compose logs postgres`
- **Slow first response**: first call to Ollama loads the model into RAM (~10s on first run, then fast)
- **Out of memory**: close Chrome tabs. `llama3.1:8b` needs ~6GB free RAM. If tight, use `phi3:mini` instead (edit `backend/app/config.py`)
