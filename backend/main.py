"""Campus Customs backend: FastAPI routes for the React desk.

Start from backend/:
    uvicorn main:app --reload --port 8000

Every shop fact and every change goes through the campus-customs MCP server.
The agents only prepare payments. Those land in a human approval queue, and
only POST /approvals/{id}/approve calls the MCP pay tools, so cash only
changes when a human clicks approve.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client
from pydantic import BaseModel, Field

from agents import MCP_SERVER, ROOT, new_run_id, run_ticket
from audit import AUDIT_PATH, AuditLog, read_audit

ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
WORKING_DB = ROOT / "data" / "campus_customs_new.db"
APPROVALS_PATH = ROOT / "output" / "approvals.json"
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# --------------------------------------------------------------------- MCP


class MCP:
    """One long-lived MCP client for the backend's own calls."""

    def __init__(self) -> None:
        self.client = Client(MCP_SERVER)
        self.lock = asyncio.Lock()

    async def call(self, tool: str, **args) -> Any:
        async with self.lock:
            result = await self.client.call_tool(tool, args, raise_on_error=False)
        if result.is_error:
            raise HTTPException(502, f"MCP tool {tool} failed: {result.content[0].text}")
        if result.data is not None:
            return result.data
        if result.structured_content is not None:
            return result.structured_content.get("result", result.structured_content)
        return json.loads(result.content[0].text)


mcp = MCP()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.client:
        yield


app = FastAPI(title="Campus Customs desk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------- run tracking

RUNS: dict[str, dict] = {}  # run_id -> {ticket_id, status, started_at, result, error}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _running_ticket_ids() -> set[int]:
    return {r["ticket_id"] for r in RUNS.values() if r["status"] == "running"}


# -------------------------------------------------------- approval queue
# Prepared payments waiting for a human. Kept in output/approvals.json so a
# backend restart doesn't lose them.

_APPROVALS_LOCK = threading.Lock()


def _load_approvals() -> list[dict]:
    if not APPROVALS_PATH.exists():
        return []
    return json.loads(APPROVALS_PATH.read_text(encoding="utf-8"))


def _save_approvals(items: list[dict]) -> None:
    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = APPROVALS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
    tmp.replace(APPROVALS_PATH)


def _same_payment(a: dict, b: dict) -> bool:
    if a["kind"] != b["kind"]:
        return False
    if a["kind"] == "invoice":
        return a.get("invoice_id") == b.get("invoice_id")
    if a["kind"] == "rent":
        return a.get("lease_id") == b.get("lease_id")
    return (a.get("vendor_id"), a.get("sku"), a.get("size")) == (b.get("vendor_id"), b.get("sku"), b.get("size"))


def _queue_payments(ticket_id: int, run_id: str, requests: list[dict]) -> list[dict]:
    """Add a run's prepared payments to the queue. A payment that is already
    pending or approved (e.g. invoice 501 queued by another ticket) is not
    queued twice."""
    audit = AuditLog(run_id, ticket_id)
    with _APPROVALS_LOCK:
        items = _load_approvals()
        next_id = max((a["id"] for a in items), default=0) + 1
        added: list[dict] = []
        for req in requests:
            dup = next(
                (a for a in items if a["status"] in ("pending", "approved") and _same_payment(a, req)),
                None,
            )
            if dup:
                audit.log("system", ["system"], "approval_queued", {
                    "skipped_duplicate_of": dup["id"], "kind": req["kind"], "amount": req["amount"],
                })
                continue
            item = {
                "id": next_id, "ticket_id": ticket_id, "run_id": run_id,
                **{k: req.get(k) for k in (
                    "kind", "amount", "reason", "invoice_id", "lease_id",
                    "vendor_id", "sku", "size", "qty", "requested_by",
                )},
                "status": "pending", "created_at": _now(),
                "depends_on": None, "decided_at": None, "approved_by": None,
                "result": None, "last_error": None,
            }
            if item["kind"] == "purchase_order":
                # A vendor won't ship while it has an open invoice, so the
                # order waits on any pending invoice payment.
                blocker = next(
                    (a for a in items + added if a["kind"] == "invoice" and a["status"] == "pending"),
                    None,
                )
                item["depends_on"] = blocker["id"] if blocker else None
            next_id += 1
            added.append(item)
            audit.log("system", ["system"], "approval_queued", {
                "approval_id": item["id"], "kind": item["kind"], "amount": item["amount"],
            })
        _save_approvals(items + added)
    return added


async def _resolve_if_done(ticket_id: int) -> bool:
    """When a ticket has no pending approvals left, mark it resolved."""
    items = [a for a in _load_approvals() if a["ticket_id"] == ticket_id]
    if not items or any(a["status"] == "pending" for a in items):
        return False
    parts = [f"#{a['id']} {a['kind']} ${a['amount']:.2f} {a['status']}" for a in items]
    await mcp.call(
        "update_ticket_status", ticket_id=ticket_id, status="resolved",
        note="Human decisions complete: " + "; ".join(parts),
    )
    return True


# ------------------------------------------------------------ background


async def _run_in_background(run_id: str, ticket_id: int) -> None:
    run = RUNS[run_id]
    try:
        result = await run_ticket(ticket_id, run_id=run_id)
        queued = _queue_payments(ticket_id, run_id, result.get("payment_requests", []))
        pending_for_ticket = [
            a for a in _load_approvals() if a["ticket_id"] == ticket_id and a["status"] == "pending"
        ]
        if pending_for_ticket:
            # Money is waiting on a human, so the ticket can't be resolved yet,
            # whatever the Boss said.
            await mcp.call(
                "update_ticket_status", ticket_id=ticket_id, status="awaiting_approval",
                note=f"{len(pending_for_ticket)} payment(s) waiting for human approval.",
            )
        elif result.get("final_status") == "resolved":
            await mcp.call(
                "update_ticket_status", ticket_id=ticket_id, status="resolved",
                note="Resolved by the agent team; no payments needed.",
            )
        run.update(status="done", result=result, approvals=queued, finished_at=_now())
    except Exception as exc:  # surfaced to the board, also in the audit trail
        run.update(status="error", error=f"{type(exc).__name__}: {exc}", finished_at=_now())


# ----------------------------------------------------------------- routes


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/tickets")
async def list_tickets() -> list[dict]:
    """All tickets with status, whether resolved, and pending approvals."""
    tickets = await mcp.call("list_tickets")
    approvals = _load_approvals()
    running = _running_ticket_ids()
    for t in tickets:
        t["resolved"] = t["status"] == "resolved"
        t["running"] = t["id"] in running
        t["pending_approvals"] = sum(
            1 for a in approvals if a["ticket_id"] == t["id"] and a["status"] == "pending"
        )
    return tickets


@app.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: int) -> dict:
    ticket = await mcp.call("get_ticket", ticket_id=ticket_id)
    if "error" in ticket:
        raise HTTPException(404, ticket["error"])
    return ticket


@app.post("/tickets/{ticket_id}/run", status_code=202)
async def run_ticket_route(ticket_id: int) -> dict:
    """Start the agent team on a ticket. Returns a run_id to poll."""
    ticket = await mcp.call("get_ticket", ticket_id=ticket_id)
    if "error" in ticket:
        raise HTTPException(404, ticket["error"])
    if ticket["status"] == "resolved":
        raise HTTPException(409, f"Ticket {ticket_id} is already resolved")
    if ticket_id in _running_ticket_ids():
        raise HTTPException(409, f"Ticket {ticket_id} is already running")
    run_id = new_run_id()
    RUNS[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running",
                    "started_at": _now(), "result": None, "error": None}
    asyncio.create_task(_run_in_background(run_id, ticket_id))
    return {"run_id": run_id, "ticket_id": ticket_id, "status": "running"}


@app.get("/runs")
async def list_runs(ticket_id: int | None = None) -> list[dict]:
    return [r for r in RUNS.values() if ticket_id is None or r["ticket_id"] == ticket_id]


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """Run status/result, plus a per-agent summary built from the audit trail."""
    events = [e for e in read_audit() if e["run_id"] == run_id]
    if run_id not in RUNS and not events:
        raise HTTPException(404, f"No run {run_id}")
    run = RUNS.get(run_id, {"run_id": run_id, "status": "unknown (from audit)"})
    return {**run, "agents": _agent_summaries(events)}


def _agent_summaries(events: list[dict]) -> list[dict]:
    """What each agent did in a run: tools used, who it delegated to, its final summary."""
    agents: dict[str, dict] = {}
    for e in events:
        if e["agent"] in ("system", "human"):
            continue
        a = agents.setdefault(e["agent"], {
            "agent": e["agent"], "tools": [], "delegated_to": [], "summary": None, "tokens": 0,
        })
        d = e["detail"]
        if e["step"] == "tool_call" and d.get("tool") not in ("delegate", "final_result"):
            if d["tool"] not in a["tools"]:
                a["tools"].append(d["tool"])
        elif e["step"] == "delegation":
            a["delegated_to"].append(d["to"])
        elif e["step"] == "model_response" and e.get("usage"):
            a["tokens"] += e["usage"]["input_tokens"] + e["usage"]["output_tokens"]
        elif e["step"] == "run_end":
            out = d.get("output", {})
            a["summary"] = out.get("summary") or out.get("outcome")
    return list(agents.values())


@app.get("/events")
async def events(
    ticket_id: int | None = None,
    run_id: str | None = None,
    since: int = Query(0, ge=0, description="Index into the audit trail; pass next_since to poll"),
    limit: int = Query(200, ge=1, le=2000),
) -> dict:
    """Recent agent events from output/audit_trail.json: which agent, what it
    said, which MCP tools it called, delegations and human approvals."""
    trail = read_audit(AUDIT_PATH)
    new = trail[since:]
    if ticket_id is not None:
        new = [e for e in new if e["ticket_id"] == ticket_id]
    if run_id is not None:
        new = [e for e in new if e["run_id"] == run_id]
    return {"events": new[-limit:], "next_since": len(trail)}


@app.get("/approvals")
async def list_approvals(
    ticket_id: int | None = None,
    status: Literal["pending", "approved", "rejected"] | None = None,
) -> list[dict]:
    return [
        a for a in _load_approvals()
        if (ticket_id is None or a["ticket_id"] == ticket_id)
        and (status is None or a["status"] == status)
    ]


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human approving")
    qty: int | None = Field(None, ge=1, description="Purchase orders only: buy fewer than prepared")


class RejectBody(BaseModel):
    rejected_by: str = Field(min_length=1)
    reason: str = ""


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: ApproveBody) -> dict:
    """The only route that moves money: a human approves a prepared payment
    and the backend calls the matching MCP pay tool."""
    items = _load_approvals()
    item = next((a for a in items if a["id"] == approval_id), None)
    if item is None:
        raise HTTPException(404, f"No approval {approval_id}")
    if item["status"] != "pending":
        raise HTTPException(409, f"Approval {approval_id} is already {item['status']}")
    dep = next((a for a in items if a["id"] == item.get("depends_on")), None)
    if dep and dep["status"] == "pending":
        raise HTTPException(409, f"Approve #{dep['id']} ({dep['kind']} ${dep['amount']:.2f}) first: "
                                 "the vendor won't ship while that invoice is open.")

    audit = AuditLog(item["run_id"], item["ticket_id"])
    if item["kind"] == "invoice":
        result = await mcp.call("pay_invoice", invoice_id=item["invoice_id"], approved_by=body.approved_by)
    elif item["kind"] == "rent":
        result = await mcp.call("pay_rent", lease_id=item["lease_id"], approved_by=body.approved_by)
    else:
        qty = item["qty"]
        if body.qty is not None:
            if body.qty > item["qty"]:
                raise HTTPException(400, f"qty can only be lowered (prepared: {item['qty']})")
            qty = body.qty
        result = await mcp.call(
            "place_purchase_order", vendor_id=item["vendor_id"], sku=item["sku"],
            size=item["size"], qty=qty, approved_by=body.approved_by,
        )

    with _APPROVALS_LOCK:
        items = _load_approvals()
        item = next(a for a in items if a["id"] == approval_id)
        if "error" in result:
            item["last_error"] = result
            _save_approvals(items)
            audit.log("human", ["human"], "approval_refused", {
                "approval_id": approval_id, "approved_by": body.approved_by, "result": result,
            })
            raise HTTPException(409, result)
        item.update(status="approved", approved_by=body.approved_by, decided_at=_now(),
                    result=result, last_error=None)
        if item["kind"] == "purchase_order":
            item["qty"], item["amount"] = result["qty"], result["amount"]
        _save_approvals(items)
    audit.log("human", ["human"], "human_approval", {
        "approval_id": approval_id, "kind": item["kind"], "amount": item["amount"],
        "approved_by": body.approved_by, "result": result,
    })
    resolved = await _resolve_if_done(item["ticket_id"])
    return {"approval": item, "ticket_resolved": resolved}


@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: RejectBody) -> dict:
    """A human declines a prepared payment. No money moves."""
    with _APPROVALS_LOCK:
        items = _load_approvals()
        item = next((a for a in items if a["id"] == approval_id), None)
        if item is None:
            raise HTTPException(404, f"No approval {approval_id}")
        if item["status"] != "pending":
            raise HTTPException(409, f"Approval {approval_id} is already {item['status']}")
        item.update(status="rejected", approved_by=body.rejected_by, decided_at=_now(),
                    result={"reason": body.reason}, last_error=None)
        _save_approvals(items)
    AuditLog(item["run_id"], item["ticket_id"]).log("human", ["human"], "human_rejection", {
        "approval_id": approval_id, "kind": item["kind"], "amount": item["amount"],
        "rejected_by": body.rejected_by, "reason": body.reason,
    })
    resolved = await _resolve_if_done(item["ticket_id"])
    return {"approval": item, "ticket_resolved": resolved}


@app.get("/cash")
async def cash() -> dict:
    """Current checking balance from cash_accounts (through MCP)."""
    data = await mcp.call("get_cash_balance")
    checking = next((a for a in data["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(500, "No checking account")
    return {"checking": checking["balance"], "as_of": checking["date"], "accounts": data["accounts"]}


@app.post("/reset")
async def reset() -> dict:
    """Copy the original database over the working copy and clear the approval
    queue. The audit trail is kept (append-only); a reset entry is added."""
    if _running_ticket_ids():
        raise HTTPException(409, "Wait for running tickets to finish before resetting")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    _save_approvals([])
    RUNS.clear()
    AuditLog(f"reset-{new_run_id()}", None).log("system", ["system"], "reset", {
        "copied": f"{ORIGINAL_DB.name} -> {WORKING_DB.name}",
    })
    return {"reset": True, "cash": await cash(), "tickets": await list_tickets()}
