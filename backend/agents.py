"""Campus Customs agent team: Boss, Inventory, Accounting, Facilities and
Customer Service.

- Every agent runs on gpt-6-luna through Portkey.
- Shop facts come only from the MCP server (mcp_server/server.py). Each agent
  sees just the MCP tools its role needs, and no agent sees the pay tools.
- Full connectivity: every agent has a `delegate` tool and can hand work to
  any other agent. Guardrails stop self-delegation, loops, deep chains and
  runaway fan-out.
- Every step of every agent loop is appended to output/audit_trail.json.

Usage:
    python agents.py --ticket 101
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import (
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from audit import AuditLog
from models import (
    AgentName,
    AgentReport,
    PaymentRequest,
    RunState,
    TeamDeps,
    TicketResolution,
)

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent
PROMPTS = BACKEND / "prompts"
MCP_SERVER = ROOT / "mcp_server" / "server.py"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# The course allows one model for every agent. Not read from the environment
# on purpose, so nobody can swap it by accident.
MODEL_NAME = "gpt-6-luna"

AGENTS: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

# Which MCP tools each role may call. Least privilege: nobody gets more than
# their job needs, and the money tools are never on this list.
TOOL_ACCESS: dict[AgentName, set[str]] = {
    "boss": {"get_shop_today", "list_tickets", "get_ticket", "update_ticket_status"},
    "inventory": {"get_ticket", "check_stock_and_pricing", "list_vendors", "check_vendor_invoices"},
    "accounting": {
        "get_ticket", "get_shop_today", "get_cash_balance", "check_stock_and_pricing",
        "list_vendors", "check_vendor_invoices", "check_rent_due",
    },
    "facilities": {"get_ticket", "get_shop_today", "check_rent_due"},
    "customer_service": {"get_ticket", "check_stock_and_pricing"},
}
HUMAN_ONLY_TOOLS = {"pay_invoice", "pay_rent", "place_purchase_order"}
assert not any(HUMAN_ONLY_TOOLS & tools for tools in TOOL_ACCESS.values())

# --- token and loop limits -------------------------------------------------
# Shared by the whole ticket run: every delegated run adds to the same usage
# counter, so one ticket can never cost more than this in total.
TICKET_LIMITS = UsageLimits(request_limit=40, tool_calls_limit=50, total_tokens_limit=150_000)
MAX_CHAIN_DEPTH = 3  # Boss -> specialist -> one more specialist
MAX_DELEGATIONS = 6  # per ticket run
MODEL_SETTINGS = OpenAIResponsesModelSettings(
    max_tokens=2_000,
    openai_reasoning_effort="low",
)
AUDIT_TEXT_LIMIT = 1_500


def load_env() -> None:
    """Read the nearest .env (walking up from backend/) without overriding
    real environment variables."""
    for folder in (BACKEND, *BACKEND.parents):
        env_path = folder / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            return


def build_model() -> OpenAIResponsesModel:
    load_env()
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is missing from the environment or .env")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": api_key},
    )
    # gpt-6-luna only supports function tools on the Responses API.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def build_mcp_toolset() -> MCPToolset:
    return MCPToolset(MCP_SERVER)


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= AUDIT_TEXT_LIMIT else text[:AUDIT_TEXT_LIMIT] + "...[clipped]"


class Team:
    """The five agents, wired to one MCP connection and to each other."""

    def __init__(self, toolset: MCPToolset | None = None):
        self.toolset = toolset or build_mcp_toolset()
        model = build_model()
        self.agents: dict[AgentName, Agent] = {}
        for name in AGENTS:
            allowed = TOOL_ACCESS[name]
            agent = Agent(
                model,
                name=name,
                deps_type=TeamDeps,
                output_type=TicketResolution if name == "boss" else AgentReport,
                instructions=(PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip(),
                toolsets=[self.toolset.filtered(lambda ctx, td, allowed=allowed: td.name in allowed)],
                model_settings=MODEL_SETTINGS,
                retries=2,
            )
            self._add_delegate_tool(agent, name)
            self.agents[name] = agent

    # --- delegation ---------------------------------------------------------

    def _add_delegate_tool(self, agent: Agent, me: AgentName) -> None:
        team = self

        @agent.tool
        async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> dict:
            """Hand a focused task to another agent and get its report back.

            to: one of boss, inventory, accounting, facilities, customer_service.
            task: what you need, with the ids/SKUs/amounts it needs to start
            (e.g. "Check stock for CC-HOOD-NAVY size M, qty 20, and which vendor can restock").
            Only delegate when the other agent's role is needed; never to yourself.
            """
            return await team._delegate(ctx, me, to, task)

    async def _delegate(self, ctx: RunContext[TeamDeps], me: AgentName, to: AgentName, task: str) -> dict:
        deps, state = ctx.deps, ctx.deps.state
        refusal = None
        if to == me:
            refusal = "You cannot delegate to yourself. Do the work with your own tools."
        elif to in deps.chain:
            refusal = f"{to} is already working on this ticket further up the chain ({' -> '.join(deps.chain)}). Answer with what you have."
        elif len(deps.chain) >= MAX_CHAIN_DEPTH:
            refusal = f"Delegation chain is already {len(deps.chain)} deep (max {MAX_CHAIN_DEPTH}). Answer with what you have."
        elif state.delegations >= MAX_DELEGATIONS:
            refusal = f"This ticket already used {MAX_DELEGATIONS} delegations. Finish with what you have."
        if refusal:
            state.audit.log(me, deps.chain, "guardrail", {"blocked_delegation_to": to, "reason": refusal})
            return {"refused": refusal}

        state.delegations += 1
        state.audit.log(me, deps.chain, "delegation", {"to": to, "task": _clip(task)})
        child = TeamDeps(state=state, chain=[*deps.chain, to])
        output = await self.run_agent(to, task, child, usage=ctx.usage)
        if isinstance(output, AgentReport):
            for req in output.payment_requests:
                req.requested_by = req.requested_by or to
            state.reports.append(output)
            state.payment_requests.extend(output.payment_requests)
        return output.model_dump(mode="json")

    # --- one agent loop, every step audited ---------------------------------

    async def run_agent(self, name: AgentName, prompt: str, deps: TeamDeps, usage=None):
        agent, audit, chain = self.agents[name], deps.state.audit, deps.chain
        audit.log(name, chain, "run_start", {"prompt": _clip(prompt), "model": MODEL_NAME})
        try:
            async with agent.iter(
                prompt, deps=deps, usage=usage, usage_limits=TICKET_LIMITS
            ) as run:
                async for node in run:
                    if Agent.is_model_request_node(node):
                        self._log_request(name, chain, audit, node.request.parts)
                    elif Agent.is_call_tools_node(node):
                        self._log_response(name, chain, audit, node.model_response)
            output = run.result.output
        except Exception as exc:
            audit.log(name, chain, "error", {"type": type(exc).__name__, "message": _clip(str(exc))})
            raise
        audit.log(name, chain, "run_end", {"output": output.model_dump(mode="json")}, _usage(run.usage))
        return output

    @staticmethod
    def _log_request(name, chain, audit, parts) -> None:
        for part in parts:
            if isinstance(part, ToolReturnPart):
                audit.log(name, chain, "tool_result", {
                    "tool": part.tool_name, "tool_call_id": part.tool_call_id,
                    "content": _clip(part.content),
                })
            elif isinstance(part, RetryPromptPart):
                audit.log(name, chain, "tool_result", {
                    "tool": part.tool_name, "retry": True, "content": _clip(part.content),
                })
        kinds = [type(p).__name__ for p in parts if not isinstance(p, (ToolReturnPart, RetryPromptPart))]
        if any(isinstance(p, UserPromptPart) for p in parts) or kinds:
            audit.log(name, chain, "model_request", {"parts": kinds})

    @staticmethod
    def _log_response(name, chain, audit, response) -> None:
        text = " ".join(p.content for p in response.parts if isinstance(p, TextPart)).strip()
        calls = [p for p in response.parts if isinstance(p, ToolCallPart)]
        audit.log(name, chain, "model_response", {
            "text": _clip(text) if text else None,
            "tool_calls": [p.tool_name for p in calls],
        }, {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens})
        for p in calls:
            audit.log(name, chain, "tool_call", {
                "tool": p.tool_name, "tool_call_id": p.tool_call_id, "args": p.args_as_dict(),
            })


def _usage(u) -> dict[str, int]:
    return {
        "requests": u.requests,
        "tool_calls": u.tool_calls,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
    }


def _merge_payment_requests(*groups: list[PaymentRequest]) -> list[PaymentRequest]:
    """Same payment prepared by two agents only shows up once for the human."""
    seen, merged = set(), []
    for group in groups:
        for req in group:
            key = (req.kind, req.invoice_id, req.lease_id, req.vendor_id, req.sku, req.size, req.qty)
            if key not in seen:
                seen.add(key)
                merged.append(req)
    return merged


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


async def run_ticket(ticket_id: int, team: Team | None = None, run_id: str | None = None) -> dict:
    """Run the whole team on one ticket, starting from the Boss."""
    run_id = run_id or new_run_id()
    audit = AuditLog(run_id, ticket_id)
    team = team or Team()
    state = RunState(run_id=run_id, ticket_id=ticket_id, audit=audit)
    deps = TeamDeps(state=state, chain=["boss"])
    prompt = (
        f"Work ticket {ticket_id}. Read it with get_ticket, decide who needs to help, "
        "delegate only to the agents this ticket actually needs, then make the final call."
    )
    try:
        async with team.toolset:
            resolution: TicketResolution = await team.run_agent("boss", prompt, deps)
    except UsageLimitExceeded as exc:
        audit.log("boss", ["boss"], "guardrail", {"limit_hit": str(exc)})
        return {
            "run_id": run_id, "ticket_id": ticket_id, "final_status": "needs_human",
            "outcome": f"Stopped: token/request limit reached ({exc}). A human should review.",
            "payment_requests": [r.model_dump(mode="json") for r in state.payment_requests],
        }
    resolution.payment_requests = _merge_payment_requests(
        resolution.payment_requests, state.payment_requests
    )
    return {"run_id": run_id, "delegations": state.delegations, **resolution.model_dump(mode="json")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team on a ticket")
    parser.add_argument("--ticket", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_ticket(args.ticket)), indent=2))


if __name__ == "__main__":
    main()
