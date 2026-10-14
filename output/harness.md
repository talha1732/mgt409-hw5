# Harness - Campus Customs Multi-Agent Operations

How to run:
1. Reset the working DB: `cp data/campus_customs.db data/campus_customs_new.db`, or **Reset DB** on the board.
2. Start the backend: from `backend/`, `uvicorn main:app --reload --port 8000`. The agents start the MCP server `mcp_server/server.py` themselves.
3. Start the board: from `frontend/`, `npm run dev`, then open http://localhost:5173.

## Database

- Original: `data/campus_customs.db`. Never edited, so we can reset from it.
- Working copy: `data/campus_customs_new.db`. The MCP server and backend read and write this file.

## Tables

| Table | Fields | Why it is useful for the agents |
|---|---|---|
| `desk` | `date_today`, `notes` | Gives the shop's "today" (2026-08-31), which every agent uses to decide what is overdue or due soon. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | The work queue. Boss reads each open ticket to decide who handles it, and the link fields point to the inventory row, lease or invoice involved. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` (key: `sku` + `size`) | Lets Inventory check stock by SKU and size and spot shortfalls. |
| `pricing` | `sku`, `unit_cost`, `list_price` | Lets Accounting work out margins before agreeing to a discount, and the cost of a restock order. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Tells Inventory which vendor can restock an item and how long it takes. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Lets Facilities see the rent amount and when it is due. |
| `cash_accounts` | `name`, `balance`, `date` | Lets Accounting check that there is enough cash before paying (no negative balances). |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | The record of every payment made, including who approved it. Starts empty and is updated when a payment goes through. |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | Shows which vendor bills are unpaid or overdue. A vendor will not ship while it has an open unpaid invoice. |

## How the 3 open tickets link to the other tables

| Ticket | What it asks | Linked rows |
|---|---|---|
| 101 `customer_order` (Tauhid Zaman) | 1 × `CC-TEE-WHITE` size S | `inventory`: tee S has qty 0, so it is out of stock. `invoice_id` 501 is $840 owed to vendor 1 (Bulldog Print Co, apparel reprint, 5 lead days). It was due 2026-08-28, so it is overdue and still `open`. The vendor will not reprint until 501 is paid. |
| 102 `rent_notice` (Elm City Properties) | Pay shop rent | `lease_id` 1: Chapel Street shop, $2,400, due 2026-09-02 (2 days after today). |
| 103 `price_override` (Yale AI Club) | 20 × `CC-HOOD-NAVY` size M at a bulk discount | `inventory`: hoodie M has qty 8, so we are 12 short. `pricing`: cost $22, list $58, so there is room for a discount. The restock comes from vendor 1, the same vendor that is blocked by invoice 501. |

**Cash check:** checking has $3,400. Paying invoice 501 ($840) and rent ($2,400) leaves $160. A restock of 12 hoodies at $22 cost is $264, which is more than the $160 left. So the agents cannot pay for everything, and a human has to decide what comes first.

## MCP server tools

Server: `mcp_server/server.py` (FastMCP), connected through `.mcp.json`. It is the **only** way the agents (and later the backend) touch `data/campus_customs_new.db`. Read tools open the database read-only.

| Tool | Tables it uses | Reads / writes | Used by | Ticket | Why it is useful |
|---|---|---|---|---|---|
| `get_shop_today` | `desk` | read | Boss, Accounting, Facilities | all | Gives the shop's "today" (2026-08-31), so overdue is judged by `desk.date_today`, not the real clock. |
| `list_tickets` | `tickets` | read | Boss | all | Shows the board: every ticket and its status. |
| `get_ticket` | `tickets`, `desk` | read | all five | all | Reads one ticket with its links (sku/size/qty, `lease_id`, `invoice_id`). |
| `check_stock_and_pricing` | `inventory`, `pricing` | read | Inventory, Accounting, Customer Service | 101, 103 | Tee size S is 0 in stock (101). Hoodie M is 12 short, with a $36/unit margin and $264 to restock (103). |
| `list_vendors` | `vendors`, `invoices` | read | Inventory, Accounting | 101, 103 | Finds the restock vendor by specialty and shows whether it can ship. |
| `check_vendor_invoices` | `vendors`, `invoices`, `desk` | read | Inventory, Accounting | 101, 103 | Shows invoice 501 ($840, 3 days overdue) blocks Bulldog Print Co from shipping. |
| `check_rent_due` | `leases`, `cash_accounts`, `desk` | read | Facilities, Accounting | 102 | $2,400 rent due 2026-09-02, 2 days away, and whether checking covers it. |
| `get_cash_balance` | `cash_accounts` | read | Accounting | all | The checking balance, checked before any payment is prepared. |
| `update_ticket_status` | `tickets` | write | Boss | all | Moves a ticket through open → in_progress → awaiting_approval → resolved, and appends a dated note. Moves no money. |
| `pay_invoice` | `invoices`, `cash_accounts`, `payments`, `desk` | write | **human only** | 101, 103 | Pays an open invoice, marks it paid, records the payment and lowers checking. |
| `pay_rent` | `leases`, `cash_accounts`, `payments`, `desk` | write | **human only** | 102 | Pays one month of rent, records the payment and moves `next_due` forward a month. |
| `place_purchase_order` | `vendors`, `invoices`, `inventory`, `pricing`, `cash_accounts`, `payments`, `desk` | write | **human only** | 101, 103 | Buys qty × `unit_cost` from a vendor. Refused while the vendor has an open invoice. Records a paid invoice and a payment. |

## Agent team

Code: `backend/agents.py`, types in `backend/models.py`, audit in `backend/audit.py`, one prompt per agent in `backend/prompts/`. Every agent runs on **gpt-6-luna** through Portkey. Run one ticket with `python backend/agents.py --ticket 101`.

| Agent | Prompt | Responsibilities | MCP tools it can call | Returns |
|---|---|---|---|---|
| Boss | `boss.md` | Reads the ticket, picks the smallest set of agents it needs, delegates, checks that the reports make sense together, sets the ticket status, makes the final call. | `get_ticket`, `list_tickets`, `get_shop_today`, `update_ticket_status` | `TicketResolution` |
| Inventory | `inventory.md` | Checks stock by SKU and size, finds shortfalls, finds the restock vendor and whether it can ship, works out the lead time. | `get_ticket`, `check_stock_and_pricing`, `list_vendors`, `check_vendor_invoices` | `AgentReport` |
| Accounting | `accounting.md` | Checks cash and invoices, does margin and discount math, **prepares** payments and purchase orders for human approval, flags cash shortfalls. | `get_ticket`, `get_shop_today`, `get_cash_balance`, `check_stock_and_pricing`, `list_vendors`, `check_vendor_invoices`, `check_rent_due` | `AgentReport` |
| Facilities | `facilities.md` | Lease, landlord, rent amount and due date. Gets the rent payment prepared by Accounting. | `get_ticket`, `get_shop_today`, `check_rent_due` | `AgentReport` |
| Customer Service | `customer_service.md` | Drafts the reply to the customer or landlord using only facts other agents confirmed. Drafts stay on the board. | `get_ticket`, `check_stock_and_pricing` | `AgentReport` |

**Delegation (full connectivity).** Every agent has a `delegate(to, task)` tool and can hand work to any other agent. A delegated agent shares the run's usage counter and audit log, and its report (with any prepared payments) comes back to the caller. Seen in the test runs:
- 102: Boss → Facilities → Accounting.
- 101: Boss → Inventory, then Boss → Accounting and Boss → Customer Service.
- 103: Boss → Inventory, Boss → Accounting, Boss → Customer Service. Customer Service then went to Accounting (for the price) and Inventory (for stock) itself.

**Data models (`backend/models.py`).**

| Model | What it is |
|---|---|
| `PaymentRequest` | A prepared payment: kind, amount, reason, and the ids it applies to. |
| `CustomerDraft` | A message draft: to, subject, body. |
| `AgentReport` | What a specialist returns. |
| `TicketResolution` | The Boss's final call. |
| `AuditEntry` | One audit step. |
| `TeamDeps` / `RunState` | The per-agent delegation chain, plus state shared across the ticket run. |

## Audit trail

`output/audit_trail.json` is a JSON list of `AuditEntry` records, one for each agent-loop step:
- `run_start`
- `model_request`
- `model_response` (text, which tools it chose, token usage)
- `tool_call` (tool and arguments)
- `tool_result`
- `delegation`
- `guardrail` (a blocked delegation or a limit hit)
- `run_end` (the structured output and cumulative usage)
- `error`

Each entry has the run id, ticket id, step number, timestamp, agent and delegation chain, e.g. `boss/facilities/accounting`. The file is append-only: each step reads the file, adds to it and writes it back atomically under a file lock, so earlier runs are never removed. An unreadable file is set aside, not overwritten.

## API routes (backend/main.py)

Start from `backend/` with `uvicorn main:app --reload --port 8000`, then open http://localhost:8000. CORS allows the Vite board at http://localhost:5173. Every route reads or changes shop data through the campus-customs MCP server, never SQLite directly.

| Method + URL | What it does |
|---|---|
| `GET /health` | Liveness check. |
| `GET /tickets` | All tickets with their status, a `resolved` flag, whether a run is in progress, and the number of pending approvals. |
| `GET /tickets/{id}` | One ticket with all its fields (sku/size/qty, lease, invoice, notes). |
| `POST /tickets/{id}/run` | Starts the agent team on a ticket in the background and returns a `run_id` (202). It refuses a ticket that is unknown (404), already resolved, or already running (409). |
| `GET /runs` / `GET /runs/{run_id}` | Run status and result, plus a summary for each agent: tools it used, who it delegated to, tokens, and its final summary. |
| `GET /events?ticket_id=&run_id=&since=&limit=` | Recent events from `output/audit_trail.json`: which agent, what it said, which MCP tools it called with what arguments, delegations, and human decisions. Poll with `since=next_since`. |
| `GET /approvals?ticket_id=&status=` | The approval queue: prepared payments and purchases waiting for a human. |
| `POST /approvals/{id}/approve` | **The only route that moves money.** A human approves with `{"approved_by": "name"}` (and an optional smaller `qty` for a purchase order). The backend calls `pay_invoice`, `pay_rent` or `place_purchase_order` through MCP, and resolves the ticket once nothing is pending. |
| `POST /approvals/{id}/reject` | A human declines a prepared payment. No money moves. The ticket resolves once nothing is pending. |
| `GET /cash` | Current checking balance from `cash_accounts` (via `get_cash_balance`). |
| `POST /reset` | Copies `campus_customs.db` over `campus_customs_new.db` and clears the approval queue. The audit trail is kept and gets a `reset` entry. |

**How a ticket flows:**
1. `POST /tickets/{id}/run`.
2. The agents prepare `PaymentRequest`s, and the backend puts them in `output/approvals.json`. A payment that is already queued (for example invoice 501, which tickets 101 and 103 both need) is not queued twice. A purchase order is linked to the pending invoice it depends on.
3. The ticket is set to `awaiting_approval` while anything is pending.
4. A human approves or rejects each payment. Cash changes only on approve.
5. When nothing is pending, the ticket is set to `resolved`.

Human approvals, rejections and refused approvals are added to the same run's audit trail as `human_approval`, `human_rejection` and `approval_refused` steps.

**Approval guardrails tested** (no payment was approved during testing):

| Attempt | Result |
|---|---|
| Purchase order approved before its invoice | 409 |
| Blank approver | 422 |
| An agent's name as approver | 409, refused by the MCP pay tool |
| Unknown approval | 404 |
| Deciding the same approval twice | 409 |
| Re-running a resolved ticket | 409 |

Cash stayed at $3,400.00 and the `payments` table stayed empty.

## Dashboard (frontend/)

React + Vite + TypeScript. Start it from `frontend/` with `npm run dev` (http://localhost:5173). It calls the backend at http://localhost:8000. The design is explained in `output/design.md`.

| Area | What it shows |
|---|---|
| Top bar | Shop date, approvals waiting, tickets resolved (x/3), **checking balance** (flashes the change after each approval), backend connection light, Reset DB |
| Ticket cards (left) | One card per ticket with a status pill (Open / Running / Needs approval / Resolved) and a "payment waiting for you" flag. Click a card to select it. |
| Ticket header (center) | Ticket facts, the **Run agent team** button, the handoff chain (e.g. Boss → Facilities → Accounting), and a resolved banner with the cash that went out |
| Agent floor | All 5 agents in their own colors: live status (thinking / using a tool / waiting on a teammate / done), a speech bubble with what they're saying or the exact tool call, **MCP tool chips**, handoff chips, tokens. Agents that aren't needed are greyed out. |
| Run report | The Boss's outcome, **one line for what each agent did** (with its tools), next steps, and the customer draft (never sent) |
| Live activity | A timeline of every audit step, including human approvals |
| Needs your approval (right) | Each prepared payment: amount, the agent that prepared it, its reason, "Checking after", a lock if it depends on another payment, a quantity slider for purchase orders, and **Approve / Reject**. A human name is required. Approve is disabled if cash would go negative. |

Everything on the board comes from the API routes above. Agent state is rebuilt from `/events` (the audit trail).

## Problem 9 run (all three tickets on the board)

1. Reset DB on the board. Starting checking was **$3,400.00**.
2. Ran 101, then 102, then 103 from the board, approving each payment as Talha Javed.

| Ticket | Handoffs | Human approvals | Cash |
|---|---|---|---|
| 101 | Boss → Inventory, Boss → Accounting, Boss → Customer Service | invoice 501 $840.00, then purchase order 1 tee $8.00 | $3,400.00 → $2,552.00 |
| 102 | Boss → Facilities → Accounting | rent $2,400.00 | → $152.00 |
| 103 | Boss → Inventory / Accounting / Customer Service; Customer Service → Accounting | 12-unit purchase order ($264.00) blocked for cash, **6 units approved ($132.00)** | → **$20.00** |

- The ending balance of $20.00 matches `cash_accounts`, and there are 4 rows in `payments`, all approved by a human.
- All three tickets are `resolved`.
- Details are in `output/desk_tickets.html` (Actual and Cash tabs), `output/resolved_tickets.json` and `output/resolved_board.html`.

## Safety rules (customers and money)

1. **Humans approve every payment.**
   - Agents can only *prepare* `PaymentRequest`s.
   - The pay tools (`pay_invoice`, `pay_rent`, `place_purchase_order`) are filtered out of every agent's toolset in code, so an agent cannot call them even if a prompt is tricked.
   - The tools also refuse an empty approver or an agent's name as `approved_by`.
2. **No negative balances.** The pay tools check checking before taking money out and refuse with the exact amount short. Accounting adds up what it prepares and flags shortfalls before a human sees them.
3. **Vendors with unpaid invoices don't ship.** `place_purchase_order` refuses while the vendor has an open invoice, and the prompts tell agents to prepare the invoice payment first.
4. **No double payments.** `pay_invoice` refuses an invoice that is already paid. Duplicate requests from different agents are merged before the human sees them.
5. **Shop date, not real date.** Overdue and due-soon are worked out from `desk.date_today`.
6. **No invented facts.** All shop data comes from MCP tools, and the prompts forbid guessing amounts, dates, vendors or SKUs. Ticket status changes go through a tool that only accepts the four valid statuses.
7. **Customers only see drafts.** Nothing is emailed, texted or called.
   - Customer Service drafts are reviewed by a human.
   - Drafts must not reveal costs, margins, cash, unpaid invoices or vendor problems.
   - Drafts must not promise dates or discounts the team didn't confirm.
8. **A ticket waiting on money isn't resolved.** The Boss sets `awaiting_approval` while any payment is pending.
9. **Least privilege.** Each agent only sees the MCP tools its role needs. Customer Service, for example, cannot see cash or invoices.
10. **Everything is auditable.** Every tool call, argument, result and delegation is in the append-only audit trail, along with every human approval or rejection.
11. **Money moves through one route only.** The agents can't reach the pay tools. The backend only calls them from `POST /approvals/{id}/approve`, which needs a named human, runs payments in dependency order (invoice before the purchase order it unblocks), and won't decide the same item twice.

## Token and cost limits

- **One model, low effort:** every agent uses gpt-6-luna with `reasoning_effort="low"` and at most 2,000 output tokens per response.
- **Shared budget per ticket:** delegated agents add to the same usage counter. One ticket is capped at 40 model requests, 50 tool calls and 150,000 total tokens (`UsageLimits`). If a limit is hit, the run stops, is logged as a `guardrail` step, and is returned as `needs_human` instead of retrying.
- **Delegation caps:**
  - At most 6 delegations per ticket.
  - The chain can be at most 3 agents deep (Boss → specialist → one more).
  - No delegating to yourself or to an agent already up the chain, which prevents loops.
  - A blocked delegation returns a refusal, so the agent answers with what it has.
- **Smallest team:** the Boss prompt asks for the fewest agents a ticket needs, not everyone on every ticket.
- **Small, targeted tools:** tools return only the rows a ticket needs, e.g. one SKU/size or one lease, never whole tables. Each agent sees only its own tools, so its tool list (and prompt) stays short.
- **Clipped audit text:** long tool results are clipped to 1,500 characters in the audit file.
- **Measured:** the Problem 9 runs used 33,375 tokens (101), 20,698 (102) and 40,877 (103), all well under the 150k cap. Per-run usage is in each `run_end` audit entry and on the agent cards.
