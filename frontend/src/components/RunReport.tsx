import type { AgentName } from "../api";
import { AGENTS, type AgentState } from "../agents";

/** After a run: the Boss's call, the customer draft, and one line per agent. */
export function RunReport({
  resolution, states, ticketResolved,
}: { resolution: Record<string, any> | null; states: Record<AgentName, AgentState>; ticketResolved: boolean }) {
  if (!resolution) return null;
  const worked = AGENTS.filter(a => states[a.name].phase !== "idle");
  const skipped = AGENTS.filter(a => states[a.name].phase === "idle");
  const draft = resolution.customer_draft;

  return (
    <section className="panel report">
      <div className="panel-head">
        <h3>Run report</h3>
        {ticketResolved ? (
          <span className="pill pill-resolved"><span className="dot" />Resolved
            {resolution.final_status !== "resolved" && " after human decision"}</span>
        ) : (
          <span className={`pill pill-${resolution.final_status === "resolved" ? "resolved" : "awaiting_approval"}`}>
            <span className="dot" />Boss: {String(resolution.final_status).replace("_", " ")}
          </span>
        )}
      </div>
      <p className="outcome-text">{resolution.outcome}</p>

      <h4>What each agent did</h4>
      <ul className="summary-list">
        {worked.map(a => (
          <li key={a.name}>
            <span className="sum-who" style={{ background: a.color }}>{a.label}</span>
            <span>
              {resolution.agent_contributions?.find((c: any) => c.agent === a.name)?.contribution
                ?? states[a.name].summary ?? "Worked on this ticket."}
              {states[a.name].tools.length > 0 && (
                <span className="muted small"> · tools: {states[a.name].tools.join(", ")}</span>
              )}
            </span>
          </li>
        ))}
        {skipped.length > 0 && (
          <li className="muted small">Not needed: {skipped.map(a => a.label).join(", ")}</li>
        )}
      </ul>

      {!ticketResolved && resolution.next_steps?.length > 0 && (
        <>
          <h4>Next steps for you</h4>
          <ul className="steps">{resolution.next_steps.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
        </>
      )}

      {draft && (
        <>
          <h4>Customer draft <span className="muted small">(stays on the board, never sent)</span></h4>
          <div className="draft">
            <div className="draft-head"><b>To:</b> {draft.to}<br /><b>Subject:</b> {draft.subject}</div>
            <div className="draft-body">{draft.body}</div>
          </div>
        </>
      )}
    </section>
  );
}
