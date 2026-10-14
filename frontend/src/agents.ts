// Who's on the team, and how to read a run's audit events as live agent state.

import type { AgentName, AuditEvent } from "./api";

export interface AgentMeta {
  name: AgentName;
  label: string;
  initials: string;
  role: string;
  color: string;
}

export const AGENTS: AgentMeta[] = [
  { name: "boss", label: "Boss", initials: "BO", role: "Reads tickets, delegates, makes the call", color: "#1d3f6e" },
  { name: "inventory", label: "Inventory", initials: "IN", role: "Stock by SKU & size, restock vendors", color: "#2f7d5b" },
  { name: "accounting", label: "Accounting", initials: "AC", role: "Cash, invoices, margins, prepares pays", color: "#b5651d" },
  { name: "facilities", label: "Facilities", initials: "FA", role: "Lease, landlord, rent", color: "#6b4fa1" },
  { name: "customer_service", label: "Customer Service", initials: "CS", role: "Drafts customer messages", color: "#c0396b" },
];

export const AGENT_BY_NAME = Object.fromEntries(AGENTS.map(a => [a.name, a])) as Record<AgentName, AgentMeta>;

export const label = (who: string) =>
  who === "human" ? "You" : who === "system" ? "Desk" : AGENT_BY_NAME[who as AgentName]?.label ?? who;

export const colorOf = (who: string) =>
  who === "human" ? "#0b7a75" : who === "system" ? "#6b7685" : AGENT_BY_NAME[who as AgentName]?.color ?? "#6b7685";

export type AgentPhase = "idle" | "thinking" | "tool" | "waiting" | "done" | "error";

export interface AgentState {
  phase: AgentPhase;
  activity: string | null;   // what they're doing / saying right now
  tools: string[];           // MCP tools used this run
  delegatedTo: string[];
  summary: string | null;    // from their final report
  tokens: number;
  calls: number;             // how many times they were brought in
}

const HIDDEN_TOOLS = new Set(["delegate", "final_result"]);

export function argsText(args: Record<string, any> | undefined): string {
  if (!args) return "";
  return Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`)
    .join(", ");
}

/** Replay one run's events into per-agent state. */
export function deriveAgents(events: AuditEvent[]): Record<AgentName, AgentState> {
  const out = Object.fromEntries(
    AGENTS.map(a => [a.name, {
      phase: "idle", activity: null, tools: [], delegatedTo: [], summary: null, tokens: 0, calls: 0,
    } as AgentState]),
  ) as Record<AgentName, AgentState>;
  const depth: Record<string, number> = {};

  for (const e of events) {
    const s = out[e.agent as AgentName];
    if (!s) continue;
    const d = e.detail;
    switch (e.step) {
      case "run_start":
        depth[e.agent] = (depth[e.agent] ?? 0) + 1;
        s.calls += 1;
        s.phase = "thinking";
        s.activity = "Reading the task…";
        break;
      case "model_response":
        if (e.usage) s.tokens += (e.usage.input_tokens ?? 0) + (e.usage.output_tokens ?? 0);
        if (d.text) s.activity = d.text;
        s.phase = "thinking";
        break;
      case "tool_call":
        if (!HIDDEN_TOOLS.has(d.tool)) {
          if (!s.tools.includes(d.tool)) s.tools.push(d.tool);
          s.phase = "tool";
          s.activity = `${d.tool}(${argsText(d.args)})`;
        } else if (d.tool === "final_result") {
          s.activity = "Writing up the report…";
        }
        break;
      case "tool_result":
        if (s.phase === "tool") s.phase = "thinking";
        if (d.tool === "delegate") {
          s.phase = "thinking";
          s.activity = "Got the report back, reviewing…";
        }
        break;
      case "delegation":
        s.delegatedTo.push(d.to);
        s.phase = "waiting";
        s.activity = `Asked ${AGENT_BY_NAME[d.to as AgentName]?.label ?? d.to}: ${d.task}`;
        break;
      case "guardrail":
        s.activity = `Guardrail: ${d.reason ?? d.limit_hit}`;
        break;
      case "run_end":
        depth[e.agent] = (depth[e.agent] ?? 1) - 1;
        s.summary = d.output?.summary ?? d.output?.outcome ?? s.summary;
        if (depth[e.agent] <= 0) {
          s.phase = "done";
          s.activity = s.summary;
        }
        break;
      case "error":
        s.phase = "error";
        s.activity = `${d.type}: ${d.message}`;
        break;
    }
  }
  return out;
}

/** The Boss's final TicketResolution for a run, if it finished. */
export function bossResolution(events: AuditEvent[]): Record<string, any> | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.agent === "boss" && e.step === "run_end") return e.detail.output ?? null;
  }
  return null;
}

/** The delegation path, e.g. ["boss → facilities", "facilities → accounting"]. */
export function handoffs(events: AuditEvent[]): { from: string; to: string; task: string }[] {
  return events
    .filter(e => e.step === "delegation")
    .map(e => ({ from: e.agent, to: e.detail.to, task: e.detail.task }));
}
