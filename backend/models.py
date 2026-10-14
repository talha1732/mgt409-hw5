"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
SPECIALISTS: tuple[AgentName, ...] = ("inventory", "accounting", "facilities", "customer_service")


class PaymentRequest(BaseModel):
    """A payment or purchase an agent has prepared. It does nothing until a
    human approves it; the approval route then calls the MCP pay tool."""

    kind: Literal["invoice", "rent", "purchase_order"]
    amount: float = Field(description="Dollar amount, taken from the database")
    reason: str = Field(description="One sentence on why this payment is needed")
    invoice_id: int | None = Field(None, description="For kind=invoice")
    lease_id: int | None = Field(None, description="For kind=rent")
    vendor_id: int | None = Field(None, description="For kind=purchase_order")
    sku: str | None = Field(None, description="For kind=purchase_order")
    size: str | None = Field(None, description="For kind=purchase_order")
    qty: int | None = Field(None, description="For kind=purchase_order")
    requested_by: AgentName | None = None


class CustomerDraft(BaseModel):
    """A message for a customer or landlord. Drafts stay on the board; they are
    never sent."""

    to: str
    subject: str
    body: str


class AgentReport(BaseModel):
    """What a specialist hands back to whoever delegated to it."""

    agent: AgentName
    summary: str = Field(description="2-4 sentences: what was checked and what was found")
    facts: list[str] = Field(default_factory=list, description="Numbers and facts read from MCP tools")
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    customer_draft: CustomerDraft | None = None
    blockers: list[str] = Field(default_factory=list, description="What stops the ticket going further")


class AgentContribution(BaseModel):
    agent: AgentName
    contribution: str


class TicketResolution(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    final_status: Literal["resolved", "awaiting_approval", "needs_human"]
    outcome: str = Field(description="2-4 sentences on what was decided and why")
    agent_contributions: list[AgentContribution]
    payment_requests: list[PaymentRequest] = Field(default_factory=list)
    customer_draft: CustomerDraft | None = None
    next_steps: list[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    """One step of an agent loop, appended to output/audit_trail.json."""

    run_id: str
    ticket_id: int | None
    seq: int
    timestamp: datetime
    agent: AgentName | Literal["human", "system"]
    chain: list[str] = Field(description="Who delegated to whom to reach this agent")
    step: Literal[
        "run_start", "model_request", "model_response", "tool_call", "tool_result",
        "delegation", "guardrail", "run_end", "error",
        "approval_queued", "human_approval", "human_rejection", "approval_refused", "reset",
    ]
    detail: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, int] | None = None


@dataclass
class RunState:
    """Shared by every agent in one ticket run."""

    run_id: str
    ticket_id: int | None
    audit: Any  # audit.AuditLog
    delegations: int = 0
    payment_requests: list[PaymentRequest] = field(default_factory=list)
    reports: list[AgentReport] = field(default_factory=list)


@dataclass
class TeamDeps:
    """Passed to each agent run. chain is this agent's own path from the Boss;
    state is shared across the whole ticket run."""

    state: RunState
    chain: list[AgentName]
