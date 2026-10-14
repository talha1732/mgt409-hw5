import { useEffect, useRef, useState } from "react";
import type { AuditEvent } from "../api";
import { money } from "../api";
import { argsText, colorOf, label } from "../agents";

function describe(e: AuditEvent): { icon: string; text: string; extra?: string } | null {
  const d = e.detail;
  switch (e.step) {
    case "run_start":
      return e.agent === "boss"
        ? { icon: "▶", text: "Picked up the ticket" }
        : { icon: "▶", text: "Started on a task", extra: d.prompt };
    case "model_response":
      return d.text ? { icon: "💬", text: d.text } : null;
    case "tool_call":
      if (d.tool === "delegate" || d.tool === "final_result") return null;
      return { icon: "⚙", text: `${d.tool}(${argsText(d.args)})` };
    case "tool_result":
      if (d.tool === "delegate" || d.tool === "final_result") return null;
      return { icon: "↩", text: `${d.tool} returned`, extra: d.content };
    case "delegation":
      return { icon: "→", text: `Handed off to ${label(d.to)}`, extra: d.task };
    case "guardrail":
      return { icon: "🛡", text: d.reason ?? d.limit_hit ?? "Guardrail" };
    case "run_end":
      return { icon: "✓", text: d.output?.summary ?? d.output?.outcome ?? "Finished" };
    case "error":
      return { icon: "⚠", text: `${d.type}: ${d.message}` };
    case "approval_queued":
      return d.skipped_duplicate_of
        ? { icon: "≡", text: `${d.kind} ${money(d.amount)} already queued as #${d.skipped_duplicate_of}` }
        : { icon: "💵", text: `Queued #${d.approval_id}: ${d.kind} ${money(d.amount)} for human approval` };
    case "human_approval":
      return { icon: "✅", text: `${d.approved_by} approved #${d.approval_id}: ${d.kind} ${money(d.amount)}` };
    case "human_rejection":
      return { icon: "✖", text: `${d.rejected_by} rejected #${d.approval_id}: ${d.kind} ${money(d.amount)}` };
    case "approval_refused":
      return { icon: "⛔", text: `Pay tool refused #${d.approval_id}: ${d.result?.error ?? ""}` };
    default:
      return null;
  }
}

export function ActivityFeed({ events, live }: { events: AuditEvent[]; live: boolean }) {
  const [showResults, setShowResults] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const rows = events
    .filter(e => showResults || e.step !== "tool_result")
    .map(e => ({ e, view: describe(e) }))
    .filter(r => r.view);

  useEffect(() => {
    if (live) end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [rows.length, live]);

  return (
    <section className="panel feed-panel">
      <div className="panel-head">
        <h3>Live activity</h3>
        <label className="toggle small">
          <input type="checkbox" checked={showResults} onChange={e => setShowResults(e.target.checked)} />
          show tool results
        </label>
      </div>
      <div className="feed">
        {rows.length === 0 && <div className="empty">Run the team on this ticket to see the agents work.</div>}
        {rows.map(({ e, view }) => (
          <div key={`${e.run_id}-${e.seq}`} className={`feed-row step-${e.step}`}>
            <span className="feed-time">{new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
            <span className="feed-who" style={{ background: colorOf(e.agent) }}>{label(e.agent)}</span>
            <span className="feed-icon">{view!.icon}</span>
            <div className="feed-text">
              <div className={e.step === "tool_call" ? "mono" : ""}>{view!.text}</div>
              {view!.extra && <div className="feed-extra">{view!.extra}</div>}
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
    </section>
  );
}
