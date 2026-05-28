# Phase 3 — Users, companies, boss admin, data isolation

Builds on Phase 1 + Phase 2. Adds the **product layer**:

- **Users + auth** — sign up, sign in, JWT tokens
- **Companies** — every user owns exactly one company with the **fixed org chart** (manager + 3 devs + sales + analyst)
- **Data isolation** — leads, drafts, chat sessions, tasks all scoped to the user's company
- **Boss admin role** — `is_admin=true` flag; bypasses isolation, can manage users, edit the org chart template
- **Company workspace UI** — login screen, top bar with company name + user menu, agent roster sidebar showing the team

Phase 1 endpoints (`/api/leads`, draft email) now require auth and filter by company.
Phase 2 endpoints (chat, tasks) same — but the chat sessions belong to the company.

## Install on top of Phase 1 + 2

Same pattern as Phase 2 — unzip over your existing project:

```bash
cd ~/path/to/phase1            # your merged Phase 1+2 dir
unzip -o ~/Downloads/phase3-users-companies.zip
cp -r phase3/* .
rm -rf phase3
```

Files **added**:
- `backend/app/db/migrate_phase3.py` — users, companies, company_members tables + adds `company_id` to existing tables
- `backend/app/auth/security.py` — password hashing, JWT
- `backend/app/auth/deps.py` — FastAPI dependencies for current_user, current_company
- `backend/app/routes/auth_routes.py`
- `backend/app/routes/company_routes.py`
- `backend/app/routes/admin_routes.py`
- `frontend/src/auth/AuthContext.jsx`
- `frontend/src/auth/LoginScreen.jsx`
- `frontend/src/components/TopBar.jsx`
- `frontend/src/components/TeamRoster.jsx`
- `frontend/src/components/AdminPanel.jsx`

Files **replaced**:
- `backend/requirements.txt` — adds `passlib[bcrypt]` and `python-jose[cryptography]`
- `backend/app/config.py` — adds JWT secret + token TTL
- `backend/app/main.py` — wires auth, mounts new routers, adds isolation guards to existing routes
- `backend/app/tools/lead_tools.py` — every query takes `company_id`
- `backend/app/tools/email_tools.py` — joins through Lead to enforce company scope
- `backend/app/agents/manager.py` — passes `company_id` into worker context
- `backend/app/agents/sales_agent.py` — uses company-scoped tools
- `frontend/src/App.jsx` — routes between login screen and main app
- `frontend/src/api/client.js` — sends auth header on every request
- `frontend/src/styles.css` — login screen + top bar styles

## Setup steps

1. Stop your backend if running.
2. Install new Python deps:
   ```bash
   cd backend && source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Pick a JWT secret. Create `backend/.env`:
   ```
   JWT_SECRET=change-me-to-something-random-and-long
   ```
   (Or just let the default dev secret stay — fine for local.)
4. Run the Phase 3 migration:
   ```bash
   python -m app.db.migrate_phase3
   ```
   This adds `users`, `companies`, `company_members`, plus a nullable `company_id` column on `leads`, `email_drafts`, `chat_sessions`. Existing Phase 1+2 data stays.
5. Bootstrap the first user (the boss):
   ```bash
   python -m app.db.bootstrap_admin
   ```
   This creates a default admin: `boss@local.dev` / `bosspass`. Change the password from the UI after first login.
6. Start the backend: `uvicorn app.main:app --reload --port 8000`
7. Refresh the frontend (or `npm run dev`).

## What you'll see

1. **Login screen** loads first.
2. **Sign up** as a normal user — your company gets created automatically with the fixed team.
3. Top bar shows your company name + the team roster on the left.
4. Phase 1 lead list, Phase 2 chat panel — all your data is isolated to your company.
5. Sign in as `boss@local` to see the **admin panel** (extra route in the top bar): user list, company list, ability to suspend users.

## The locked org chart

When a user signs up, this is created server-side and **cannot be modified by the user**:

```
company {
  manager        (1 agent)
  sales          (1 agent)
  dev_backend    (1 agent)
  dev_frontend   (1 agent)
  dev_qa         (1 agent)
  social_analyst (1 agent)
}
```

The template lives in `backend/app/db/org_chart.py`. Users have read-only access. Only `is_admin=true` users can mutate it via `/api/admin/template`.

## Data isolation model

Every query that returns user-visible data has a `WHERE company_id = :company_id` clause. The dependency `get_current_company()` resolves the company from the JWT, and FastAPI's `Depends()` system injects it everywhere.

Boss admin bypasses isolation via a separate dependency `get_company_or_admin_override()` that accepts an optional `?company_id=X` query param for admins only.

## Phase 4 preview

Phase 4 is cost optimization + observability — the model router, semantic cache, per-company token budgets, and reusing AgentLens for tracing. The `company_id` you have now is exactly the unit budgets will be applied to.
