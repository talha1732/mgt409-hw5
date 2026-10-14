# Campus Customs MCP Server

A [FastMCP](https://gofastmcp.com) server that is the **only** way the Campus Customs agent team (and the backend) reads or changes shop data. Every value it returns comes straight from the database.

## Database

The server uses `data/campus_customs_new.db`, the working copy of the shop database. The original `data/campus_customs.db` is never touched. To reset, copy it over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

"Today" for the shop is `desk.date_today` (2026-08-31), not the computer's clock. Any "overdue" or "days until due" value is worked out from that date.

## Tools

### Read tools (database opened read-only)

| Tool | Inputs | Tables | Ticket | What it returns |
|---|---|---|---|---|
| `get_shop_today` | none | `desk` | all | The shop's today and desk notes |
| `list_tickets` | `status` (optional) | `tickets` | all | id, type, requester, subject, status for every ticket |
| `get_ticket` | `ticket_id` | `tickets`, `desk` | all | Every ticket field, including linked sku/size/qty, `lease_id` and `invoice_id` |
| `check_stock_and_pricing` | `sku`, `size`, `qty_needed` | `inventory`, `pricing` | 101, 103 | Qty on hand, shortfall, unit cost, list price, margin, and restock cost for the shortfall |
| `list_vendors` | none | `vendors`, `invoices` | 101, 103 | Each vendor's specialty, lead days, open invoice total, and `can_ship` |
| `check_vendor_invoices` | `vendor_id` or `invoice_id` | `vendors`, `invoices`, `desk` | 101, 103 | One vendor's open invoices with days overdue, and `can_ship` |
| `check_rent_due` | `lease_id` | `leases`, `cash_accounts`, `desk` | 102 | Rent amount, due date, days until due, and whether cash covers it |
| `get_cash_balance` | none | `cash_accounts` | all | Every account balance and total cash |

### Write tools

| Tool | Inputs | Tables | Who may call it | What it does |
|---|---|---|---|---|
| `update_ticket_status` | `ticket_id`, `status`, `note` | `tickets` | Boss agent | Sets status (`open` / `in_progress` / `awaiting_approval` / `resolved`) and appends a dated note. Moves no money. |
| `pay_invoice` | `invoice_id`, `approved_by` | `invoices`, `cash_accounts`, `payments` | **Human only** | Pays an open invoice, marks it `paid`, records a payment, lowers checking |
| `pay_rent` | `lease_id`, `approved_by` | `leases`, `cash_accounts`, `payments` | **Human only** | Pays one month's rent, records a payment, moves `next_due` forward a month |
| `place_purchase_order` | `vendor_id`, `sku`, `size`, `qty`, `approved_by` | `vendors`, `invoices`, `inventory`, `pricing`, `cash_accounts`, `payments` | **Human only** | Pays qty × unit_cost to the vendor and records it as a paid invoice plus a payment. Stock arrives after `lead_days`. |

## Money guardrails (built into the pay tools)

- `approved_by` must be a human's name. An empty value or an agent name (boss, accounting, ...) is refused.
- If checking can't cover the amount, the tool refuses and reports how much is short. Balances never go negative.
- `place_purchase_order` is refused while the vendor has any open unpaid invoice.
- An invoice that is already paid can't be paid again.
- The agents' toolsets filter out all three pay tools (`backend/agents.py`). Only the human-approval step in the backend calls them.

## Setup

```bash
pip install -r requirements.txt
python mcp_server/server.py   # runs over stdio
```

The project's `.mcp.json` registers this server as `campus-customs` for Claude Code. The agents in `backend/` start it themselves over stdio.
