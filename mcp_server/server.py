"""Campus Customs MCP server.

The only way the agent team (and the backend) touches
data/campus_customs_new.db. Every value returned comes straight from the
database; nothing is invented.

Read tools open the database read-only. The write tools are:
  - update_ticket_status: agents may use it to move a ticket along.
  - pay_invoice / pay_rent / place_purchase_order: money tools. They require
    a human approver name, refuse if cash would go negative, and are hidden
    from the agents. Only the human-approval route in the backend calls them.
"""

import calendar
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

# Keep stdio quiet when the agents launch the server.
os.environ.setdefault("FASTMCP_LOG_LEVEL", "WARNING")

from fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"

TICKET_STATUSES = ("open", "in_progress", "awaiting_approval", "resolved")
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service", "customer service", "agent"}
CASH_ACCOUNT = "checking"

mcp = FastMCP("campus-customs")


def _connect(write: bool = False) -> sqlite3.Connection:
    mode = "rw" if write else "ro"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _today(conn: sqlite3.Connection) -> date:
    """The shop's 'today' comes from desk.date_today, not the real clock."""
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return date.fromisoformat(row["date_today"])


def _check_approver(approved_by: str) -> str | None:
    """Payments need a named human. Returns an error message, or None if OK."""
    name = (approved_by or "").strip()
    if not name:
        return "Refused: payments need human approval (approved_by is empty)."
    if name.lower() in AGENT_NAMES:
        return f"Refused: '{name}' is an agent, not a human approver."
    return None


def _withdraw(conn: sqlite3.Connection, amount: float, today: date) -> dict | None:
    """Take cash out of checking. Returns an error dict if it would go negative."""
    row = conn.execute(
        "SELECT balance FROM cash_accounts WHERE name = ?", (CASH_ACCOUNT,)
    ).fetchone()
    if row is None:
        return {"error": f"No cash account named {CASH_ACCOUNT}"}
    if row["balance"] < amount:
        return {
            "error": "Refused: not enough cash. No negative balances.",
            "balance": row["balance"],
            "amount": amount,
            "short_by": round(amount - row["balance"], 2),
        }
    conn.execute(
        "UPDATE cash_accounts SET balance = ROUND(balance - ?, 2), date = ? WHERE name = ?",
        (amount, today.isoformat(), CASH_ACCOUNT),
    )
    return None


def _record_payment(conn, kind: str, ref_id: int, amount: float, today: date, approved_by: str) -> int:
    cur = conn.execute(
        "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kind, ref_id, amount, CASH_ACCOUNT, today.isoformat(), approved_by.strip()),
    )
    return cur.lastrowid


def _balance(conn) -> float:
    return conn.execute(
        "SELECT balance FROM cash_accounts WHERE name = ?", (CASH_ACCOUNT,)
    ).fetchone()["balance"]


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


# ---------------------------------------------------------------- read tools


@mcp.tool
def get_shop_today() -> dict:
    """Return the shop's 'today' (desk.date_today) and any desk notes.

    Always use this date, never the real clock, to decide what is overdue.
    """
    with _connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk LIMIT 1").fetchone()
    return {"date_today": row["date_today"], "notes": row["notes"]}


@mcp.tool
def list_tickets(status: str | None = None) -> list[dict]:
    """List tickets on the board (id, type, requester, subject, status).

    Pass status (open, in_progress, awaiting_approval, resolved) to filter.
    """
    query = "SELECT id, type, requester, subject, status, created_at FROM tickets"
    args: tuple = ()
    if status:
        query += " WHERE status = ?"
        args = (status,)
    with _connect() as conn:
        rows = conn.execute(query + " ORDER BY id", args).fetchall()
    return [dict(r) for r in rows]


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Return every field of one ticket, including the linked sku/size/qty,
    lease_id and invoice_id, plus the shop's today.
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"error": f"No ticket with id={ticket_id}"}
        today = _today(conn)
    return {**dict(row), "shop_today": today.isoformat()}


@mcp.tool
def check_stock_and_pricing(sku: str, size: str, qty_needed: int) -> dict:
    """Check stock for a SKU and size, the shortfall against qty_needed, and the
    unit cost, list price and margin for that SKU.

    Use for customer orders (ticket 101) and bulk or discount requests (ticket 103).
    """
    with _connect() as conn:
        item = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if item is None:
            return {"error": f"No inventory row for sku={sku} size={size}"}

        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()

    shortfall = max(qty_needed - item["qty"], 0)
    result = {
        "sku": item["sku"],
        "name": item["name"],
        "size": item["size"],
        "location": item["location"],
        "qty_on_hand": item["qty"],
        "qty_needed": qty_needed,
        "shortfall": shortfall,
        "in_stock_for_request": shortfall == 0,
    }
    if price is None:
        result["pricing"] = None
    else:
        margin = price["list_price"] - price["unit_cost"]
        result["pricing"] = {
            "unit_cost": price["unit_cost"],
            "list_price": price["list_price"],
            "margin_per_unit": round(margin, 2),
            "margin_pct": round(margin / price["list_price"] * 100, 1),
            "restock_cost_for_shortfall": round(shortfall * price["unit_cost"], 2),
        }
    return result


@mcp.tool
def check_vendor_invoices(vendor_id: int | None = None, invoice_id: int | None = None) -> dict:
    """Look up a vendor (by vendor_id, or via one of its invoice_id) and list its
    unpaid invoices, how overdue each one is, and whether the vendor can ship.

    A vendor will not ship new product while it has an open unpaid invoice.
    Use for ticket 101 (invoice 501 blocks the tee reprint).
    """
    if vendor_id is None and invoice_id is None:
        return {"error": "Pass vendor_id or invoice_id"}

    with _connect() as conn:
        today = _today(conn)
        if vendor_id is None:
            inv = conn.execute(
                "SELECT vendor_id FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            if inv is None:
                return {"error": f"No invoice with id={invoice_id}"}
            vendor_id = inv["vendor_id"]

        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if vendor is None:
            return {"error": f"No vendor with id={vendor_id}"}

        open_rows = conn.execute(
            "SELECT id, amount, due_date, status, description FROM invoices "
            "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
            (vendor_id,),
        ).fetchall()

    open_invoices = []
    for r in open_rows:
        days_overdue = (today - date.fromisoformat(r["due_date"])).days
        open_invoices.append({
            "invoice_id": r["id"],
            "amount": r["amount"],
            "due_date": r["due_date"],
            "status": r["status"],
            "description": r["description"],
            "days_overdue": max(days_overdue, 0),
            "is_overdue": days_overdue > 0,
        })

    return {
        "today": today.isoformat(),
        "vendor_id": vendor["id"],
        "vendor_name": vendor["name"],
        "specialty": vendor["specialty"],
        "lead_days": vendor["lead_days"],
        "open_invoices": open_invoices,
        "total_open_amount": round(sum(i["amount"] for i in open_invoices), 2),
        "can_ship": len(open_invoices) == 0,
    }


@mcp.tool
def check_rent_due(lease_id: int) -> dict:
    """Look up a lease's rent amount and due date, how many days until it is due,
    and whether the cash accounts can cover it.

    Read-only: this does not pay anything. Payments need human approval.
    Use for ticket 102 (rent notice).
    """
    with _connect() as conn:
        today = _today(conn)
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return {"error": f"No lease with id={lease_id}"}

        accounts = conn.execute(
            "SELECT name, balance, date FROM cash_accounts"
        ).fetchall()

    days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
    return {
        "today": today.isoformat(),
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": lease["monthly_rent"],
        "next_due": lease["next_due"],
        "days_until_due": days_until_due,
        "is_overdue": days_until_due < 0,
        "cash_accounts": [
            {
                "name": a["name"],
                "balance": a["balance"],
                "as_of": a["date"],
                "can_cover_rent": a["balance"] >= lease["monthly_rent"],
                "balance_after_rent": round(a["balance"] - lease["monthly_rent"], 2),
            }
            for a in accounts
        ],
    }


@mcp.tool
def list_vendors() -> list[dict]:
    """List every vendor with specialty, lead days, open unpaid invoice total,
    and can_ship (false while any invoice is open).

    Use to find which vendor can restock an item.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT v.id, v.name, v.specialty, v.lead_days, "
            "COUNT(i.id) AS open_invoice_count, COALESCE(SUM(i.amount), 0) AS open_invoice_total "
            "FROM vendors v LEFT JOIN invoices i ON i.vendor_id = v.id AND i.status = 'open' "
            "GROUP BY v.id ORDER BY v.id"
        ).fetchall()
    return [
        {**dict(r), "can_ship": r["open_invoice_count"] == 0}
        for r in rows
    ]


@mcp.tool
def get_cash_balance() -> dict:
    """Return every cash account balance and the total cash on hand."""
    with _connect() as conn:
        rows = conn.execute("SELECT name, balance, date FROM cash_accounts").fetchall()
    return {
        "accounts": [dict(r) for r in rows],
        "total_cash": round(sum(r["balance"] for r in rows), 2),
    }


# --------------------------------------------------------------- write tools


@mcp.tool
def update_ticket_status(ticket_id: int, status: str, note: str) -> dict:
    """Set a ticket's status and append a short note to it.

    status must be one of: open, in_progress, awaiting_approval, resolved.
    Does not move any money.
    """
    if status not in TICKET_STATUSES:
        return {"error": f"status must be one of {TICKET_STATUSES}"}
    with _connect(write=True) as conn:
        row = conn.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"error": f"No ticket with id={ticket_id}"}
        today = _today(conn)
        notes = (row["notes"] or "").rstrip()
        notes = f"{notes}\n[{today.isoformat()}] {status}: {note.strip()}".strip()
        conn.execute(
            "UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes, ticket_id)
        )
    return {"ticket_id": ticket_id, "status": status, "notes": notes}


@mcp.tool
def pay_invoice(invoice_id: int, approved_by: str) -> dict:
    """HUMAN-APPROVED ONLY. Pay an open vendor invoice in full from checking.

    Marks the invoice paid, records a payment row, and lowers the checking
    balance. Refuses without a human approver or if cash would go negative.
    """
    if err := _check_approver(approved_by):
        return {"error": err}
    with _connect(write=True) as conn:
        today = _today(conn)
        inv = conn.execute(
            "SELECT id, vendor_id, amount, status FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if inv is None:
            return {"error": f"No invoice with id={invoice_id}"}
        if inv["status"] != "open":
            return {"error": f"Invoice {invoice_id} is already {inv['status']}"}
        if err := _withdraw(conn, inv["amount"], today):
            return err
        conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))
        payment_id = _record_payment(conn, "invoice", invoice_id, inv["amount"], today, approved_by)
        balance = _balance(conn)
    return {
        "payment_id": payment_id,
        "invoice_id": invoice_id,
        "vendor_id": inv["vendor_id"],
        "amount": inv["amount"],
        "approved_by": approved_by.strip(),
        "paid_at": today.isoformat(),
        "checking_balance_after": balance,
    }


@mcp.tool
def pay_rent(lease_id: int, approved_by: str) -> dict:
    """HUMAN-APPROVED ONLY. Pay one month of rent on a lease from checking.

    Records a payment row, lowers the checking balance, and moves the lease's
    next_due forward one month. Refuses without a human approver or if cash
    would go negative.
    """
    if err := _check_approver(approved_by):
        return {"error": err}
    with _connect(write=True) as conn:
        today = _today(conn)
        lease = conn.execute(
            "SELECT id, monthly_rent, next_due FROM leases WHERE id = ?", (lease_id,)
        ).fetchone()
        if lease is None:
            return {"error": f"No lease with id={lease_id}"}
        if err := _withdraw(conn, lease["monthly_rent"], today):
            return err
        new_due = _add_month(date.fromisoformat(lease["next_due"])).isoformat()
        conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, lease_id))
        payment_id = _record_payment(conn, "rent", lease_id, lease["monthly_rent"], today, approved_by)
        balance = _balance(conn)
    return {
        "payment_id": payment_id,
        "lease_id": lease_id,
        "amount": lease["monthly_rent"],
        "paid_period_due": lease["next_due"],
        "next_due": new_due,
        "approved_by": approved_by.strip(),
        "paid_at": today.isoformat(),
        "checking_balance_after": balance,
    }


@mcp.tool
def place_purchase_order(vendor_id: int, sku: str, size: str, qty: int, approved_by: str) -> dict:
    """HUMAN-APPROVED ONLY. Buy qty units of sku/size from a vendor at unit_cost
    and pay for it now from checking.

    Refuses if the vendor still has an open unpaid invoice, without a human
    approver, or if cash would go negative. Records the order as a paid
    invoice plus a payment row. Stock arrives after the vendor's lead_days,
    so inventory qty is not changed here.
    """
    if err := _check_approver(approved_by):
        return {"error": err}
    if qty <= 0:
        return {"error": "qty must be positive"}
    with _connect(write=True) as conn:
        today = _today(conn)
        vendor = conn.execute(
            "SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if vendor is None:
            return {"error": f"No vendor with id={vendor_id}"}
        blocking = conn.execute(
            "SELECT id, amount FROM invoices WHERE vendor_id = ? AND status = 'open'", (vendor_id,)
        ).fetchall()
        if blocking:
            return {
                "error": f"Refused: {vendor['name']} will not ship while it has open unpaid invoices.",
                "open_invoices": [dict(b) for b in blocking],
            }
        if conn.execute(
            "SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone() is None:
            return {"error": f"No inventory row for sku={sku} size={size}"}
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            return {"error": f"No pricing for sku={sku}"}
        amount = round(price["unit_cost"] * qty, 2)
        if err := _withdraw(conn, amount, today):
            return err
        cur = conn.execute(
            "INSERT INTO invoices (vendor_id, amount, due_date, status, description) "
            "VALUES (?, ?, ?, 'paid', ?)",
            (vendor_id, amount, today.isoformat(), f"Purchase order {qty} x {sku} {size}"),
        )
        invoice_id = cur.lastrowid
        payment_id = _record_payment(conn, "purchase_order", invoice_id, amount, today, approved_by)
        balance = _balance(conn)
    return {
        "payment_id": payment_id,
        "invoice_id": invoice_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor["name"],
        "sku": sku,
        "size": size,
        "qty": qty,
        "unit_cost": price["unit_cost"],
        "amount": amount,
        "expected_arrival": (today + timedelta(days=vendor["lead_days"])).isoformat(),
        "approved_by": approved_by.strip(),
        "checking_balance_after": balance,
    }


if __name__ == "__main__":
    mcp.run(show_banner=False)
