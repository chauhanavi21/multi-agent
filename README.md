# Phase 2 — Multi-agent team (manager + 3 devs + analyst + sales)

Builds on Phase 1. Same Postgres, same Ollama, same FastAPI app. Adds:

- **Manager agent** (supervisor) — decomposes user requests into subtasks, routes to specialists, synthesizes results
- **Dev agents x3** — backend, frontend, QA — each with its own tools and system prompt
- **Social analyst** — Facebook + Instagram trend analysis (mocked APIs, ready for real Meta Graph API later)
- **Sales agent** — your Phase 1 agent, now a worker the manager can call
- **Task queue** — every agent action goes through a Postgres table so runs are replayable and auditable
- **Chat UI** — talk to the manager in natural language; watch each subtask stream live

## How to apply Phase 2 on top of Phase 1

This zip contains **only the new/changed files**. Copy them over your existing Phase 1 directory — nothing in Phase 1 gets deleted, only added to.

```bash
# Assuming your Phase 1 lives in ~/projects/phase1
cd ~/projects/phase1

# Unzip phase 2 over it (will only add new files + replace main.py, App.jsx, sales_agent.py)
unzip -o ~/Downloads/phase2-multiagent.zip
```

Files changed from Phase 1:
- `backend/app/main.py` (adds new routes, keeps old ones)
- `backend/app/agents/sales_agent.py` (refactored to be a callable worker, **plus** the original endpoints still work)
- `backend/requirements.txt` (no new deps actually — same versions work)
- `frontend/src/App.jsx` (adds chat panel)
- `frontend/src/styles.css` (adds chat styles)

Files added:
- `backend/app/agents/manager.py` — supervisor agent + LangGraph orchestrator
- `backend/app/agents/dev_backend.py`
- `backend/app/agents/dev_frontend.py`
- `backend/app/agents/dev_qa.py`
- `backend/app/agents/social_analyst.py`
- `backend/app/agents/base.py` — shared worker contract
- `backend/app/agents/registry.py` — agent lookup + capabilities
- `backend/app/tools/dev_tools.py` — sandboxed code/spec tools
- `backend/app/tools/social_tools.py` — mocked FB/IG trend data
- `backend/app/tools/task_queue.py` — Postgres task queue
- `backend/app/db/migrate_phase2.py` — adds new tables, keeps Phase 1 data
- `frontend/src/components/ChatPanel.jsx`
- `frontend/src/components/TaskKanban.jsx`
- `frontend/src/components/AgentBadge.jsx`

## Steps to run Phase 2

1. Stop Phase 1 backend if running (`Ctrl+C` the uvicorn process). Frontend can stay.
2. Make sure Postgres + Ollama are still up: `docker compose ps`, `ollama list`.
3. Pull one more model for the manager (better tool calling): `ollama pull qwen2.5:7b` — already in your Phase 1 list but skip if you skipped it then.
4. Apply migrations (additive, won't drop Phase 1 data):
   ```bash
   cd backend
   source venv/bin/activate
   python -m app.db.migrate_phase2
   ```
5. Restart backend: `uvicorn app.main:app --reload --port 8000`
6. Frontend: `npm run dev` (or refresh if already running)
7. Open http://localhost:5173 — you'll now see a chat panel on the right side.

## Try these prompts in the chat

- "Draft cold emails for everyone in fintech"
- "What's trending on Instagram for B2B SaaS this week?"
- "Spec out a backend endpoint for tracking email opens"
- "Find 3 new leads in healthtech, then draft an outreach for each"
- "Review the lead status workflow for issues"

The manager decides which agents to call, runs them, and shows you everything in the kanban.

## How the supervisor pattern works

```
                user message
                     │
                     ▼
              ┌──────────────┐
              │   manager    │  decomposes into tasks
              └──────┬───────┘  picks workers + parallelism
                     │
        ┌────────────┼────────────┬────────────┐
        ▼            ▼            ▼            ▼
   [sales]    [dev_backend]   [analyst]    [dev_qa]
        │            │            │            │
        └────────────┴────────────┴────────────┘
                     │
                     ▼
              ┌──────────────┐
              │  aggregator  │  manager re-enters
              └──────┬───────┘  to synthesize results
                     │
                     ▼
              streamed answer
```

The manager calls a single LLM with strict JSON output to produce a task plan:
```json
{
  "tasks": [
    {"id": "t1", "agent": "sales", "action": "draft_email", "input": {...}, "depends_on": []},
    {"id": "t2", "agent": "social_analyst", "action": "trend_report", "input": {...}, "depends_on": []},
    {"id": "t3", "agent": "dev_qa", "action": "review", "input": {...}, "depends_on": ["t1"]}
  ]
}
```

Tasks with no `depends_on` run in parallel via `asyncio.gather`. The DAG executor handles the rest.

## What's deliberately faked

- **Dev agents don't execute code**. They produce specs, diffs, and review notes. Real code execution is a Phase 4 concern (sandboxing, security).
- **Social analyst** returns mock trend data from `social_tools.py`. Wire to real Meta Graph API in Phase 5.
- **Manager doesn't call itself recursively** yet. Single-level decomposition. Recursive planning is Phase 4.

## Phase 3 preview

Phase 3 wraps this with users, companies, auth, and a proper dashboard. The `chat_sessions` table already has a nullable `user_id` and `company_id` — Phase 3 just fills those in.
