# Campus Customs Multi-Agent Operations (MGT 409 · HW5)

A five-agent team runs the Campus Customs shop desk. The **Boss** reads each ticket and delegates to **Inventory**, **Accounting**, **Facilities** and **Customer Service**. The agents get every shop fact through an **MCP server** over a SQLite database. A **FastAPI backend** runs the team and holds a human approval queue, and a **React dashboard** lets a person watch the agents and approve payments.

Agents only *prepare* payments. Cash changes only when a human clicks **Approve** on the board.

```
.
├── AI_prompts.md            prompts I gave my vibe coder, per problem
├── requirements.txt         Python dependencies
├── .env.example             environment variables (copy to .env)
├── .mcp.json                registers the MCP server with Claude Code
├── data/
│   ├── campus_customs.db        original shop database (never modified)
│   └── campus_customs_new.db    working copy the app reads and writes
├── mcp_server/              FastMCP server: 12 tools over the working DB
│   ├── server.py
│   └── README.md
├── backend/                 FastAPI + PydanticAI agent team
│   ├── main.py              API routes
│   ├── agents.py            the 5 agents, delegation, guardrails, token limits
│   ├── models.py            Pydantic data models
│   ├── audit.py             append-only audit trail
│   └── prompts/             boss.md, inventory.md, accounting.md, facilities.md, customer_service.md
├── frontend/                React + Vite + TypeScript ops dashboard
└── output/
    ├── harness.md               tables, MCP tools, agents, routes, dashboard, safety, token limits
    ├── mcp_smoke.json           MCP tool smoke test (Problem 4)
    ├── desk_tickets.html        Expected / Actual per ticket + Cash + Reflection tabs
    ├── design.md                dashboard design notes
    ├── resolved_tickets.json    outcome, agent work and human approvals per ticket
    ├── resolved_board.html      dashboard screenshots after each ticket resolved
    ├── audit_trail.json         every agent-loop step and human decision (append-only)
    ├── approvals.json           the approval queue from the final run
    └── github_url.txt
```

## 1. Install the dependencies

You need Python 3.11+ and Node.js 20+.

```bash
# from the project root
pip install -r requirements.txt

cd frontend
npm install
cd ..
```

## 2. Configure the environment variables

```bash
cp .env.example .env
```

Then open `.env` and set `PORTKEY_API_KEY` to your Portkey key. Every agent uses **gpt-6-luna** through Portkey (`https://api.portkey.ai/v1`). The backend looks for `.env` in `backend/` and then in each folder above it, so a `.env` in the project root works. `.env` is git-ignored, so it never gets committed.

## 3. Copy the original database to the working database (fresh run)

The app only reads and writes `data/campus_customs_new.db`. `data/campus_customs.db` is the untouched original. To start clean:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

> The working DB in this repo is the state **after** my final run: all 3 tickets resolved and checking at $20.00. That is the state described in `output/desk_tickets.html`. Copy the original over it before a fresh run.

## 4. Start the MCP server

```bash
python mcp_server/server.py
```

This runs the server over stdio, which is useful for testing it on its own. **You don't need to leave it running for the app.** The agents and the backend start `mcp_server/server.py` themselves over stdio whenever they need it. `.mcp.json` registers the same server as `campus-customs` for Claude Code (open the project in Claude Code and approve the server). The tools are listed in `mcp_server/README.md`.

## 5. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The backend runs at http://localhost:8000 (interactive docs at http://localhost:8000/docs) and allows requests from the Vite board at http://localhost:5173. The routes are listed in `output/harness.md`.

You can also run one ticket without the UI: `python backend/agents.py --ticket 101`. This prints the Boss's resolution; payments it prepares are not queued or paid.

## 6. Start the React dashboard

In a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The board talks to the backend at http://localhost:8000.

## 7. Reset the database and run all 3 tickets again

1. With the backend and the board running, click **Reset DB** in the board's top bar. This copies `campus_customs.db` over `campus_customs_new.db` and clears the approval queue. You can also run `curl -X POST http://localhost:8000/reset`, or stop the backend and run the `cp` command from step 3. Checking should read **$3,400.00** and all three tickets **Open**.
2. Type your name in **Approving as** on the right.
3. Click ticket **#101** and then **▶ Run agent team**. Watch the agent floor and live activity. When it shows *Needs approval*, approve **invoice 501 ($840)** first, then the **$8 tee order**, which stays locked until the invoice is paid.
4. Click **#102**, run it, and approve the **$2,400 rent**.
5. Click **#103** and run it. Accounting prepares a 12-hoodie order ($264) but only $152 is left, so Approve is disabled. Use the quantity slider to approve what cash can cover, or reject it.
6. Each ticket turns **Resolved** when nothing is pending. The checking balance in the top bar always matches `cash_accounts`.

The audit trail (`output/audit_trail.json`) is append-only. Every run and every human decision is added to it, and resets never delete it.

## Safety

- Agents can't see the pay tools. Payments run only from `POST /approvals/{id}/approve` with a named human approver.
- The pay tools refuse negative balances, agent names as approvers, double payments, and purchase orders while the vendor has an open invoice.
- Customer messages are drafts and are never sent.
- Each ticket is capped at 40 model requests, 50 tool calls and 150k tokens, plus delegation limits.

Details are in `output/harness.md`.
