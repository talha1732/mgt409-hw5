import type { AgentName } from "../api";
import { AGENTS, AGENT_BY_NAME, type AgentState } from "../agents";

const PHASE_LABEL: Record<string, string> = {
  idle: "Not on this ticket",
  thinking: "Thinking",
  tool: "Using a tool",
  waiting: "Waiting on a teammate",
  done: "Done",
  error: "Error",
};

export function AgentFloor({ states, live }: { states: Record<AgentName, AgentState>; live: boolean }) {
  const active = AGENTS.filter(a => states[a.name].phase !== "idle").length;
  return (
    <section className="panel">
      <div className="panel-head">
        <h3>Agent floor</h3>
        <span className="muted small">
          {active === 0 ? "Nobody has picked this up yet" : `${active} of 5 agents brought in`}
          {live && <span className="live-dot" title="Live" />}
        </span>
      </div>
      <div className="agent-grid">
        {AGENTS.map(meta => {
          const s = states[meta.name];
          const working = s.phase === "thinking" || s.phase === "tool" || s.phase === "waiting";
          return (
            <article
              key={meta.name}
              className={`agent-card phase-${s.phase} ${working ? "working" : ""}`}
              style={{ ["--agent" as string]: meta.color }}
            >
              <header>
                <span className="avatar">{meta.initials}</span>
                <div>
                  <div className="agent-name">{meta.label}</div>
                  <div className="agent-role">{meta.role}</div>
                </div>
              </header>
              <div className="agent-phase">
                <span className="phase-dot" />
                {PHASE_LABEL[s.phase]}
                {s.calls > 1 && <span className="muted"> · called {s.calls}×</span>}
              </div>
              <div className={`bubble ${s.phase === "tool" ? "mono" : ""}`}>
                {s.activity ?? (s.phase === "idle" ? "—" : "…")}
              </div>
              {s.tools.length > 0 && (
                <div className="chips">
                  {s.tools.map(t => <span key={t} className="chip tool">⚙ {t}</span>)}
                </div>
              )}
              {s.delegatedTo.length > 0 && (
                <div className="chips">
                  {s.delegatedTo.map((d, i) => (
                    <span key={i} className="chip handoff" style={{ ["--to" as string]: AGENT_BY_NAME[d as AgentName]?.color }}>
                      → {AGENT_BY_NAME[d as AgentName]?.label ?? d}
                    </span>
                  ))}
                </div>
              )}
              {s.tokens > 0 && <div className="agent-foot">{s.tokens.toLocaleString()} tokens</div>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
