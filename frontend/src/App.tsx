import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE, api, money, type Approval, type AuditEvent, type Cash, type Ticket, type TicketDetail,
} from "./api";
import { AGENT_BY_NAME, bossResolution, deriveAgents, handoffs } from "./agents";
import { TicketList, StatusPill } from "./components/TicketList";
import { AgentFloor } from "./components/AgentFloor";
import { ActivityFeed } from "./components/ActivityFeed";
import { Approvals } from "./components/Approvals";
import { CashTile } from "./components/CashTile";
import { RunReport } from "./components/RunReport";
import type { AgentName } from "./api";

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [cash, setCash] = useState<Cash | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const cursor = useRef(0);

  const flash = (kind: "ok" | "err", text: string) => {
    setNotice({ kind, text });
    setTimeout(() => setNotice(null), 5000);
  };

  // --- polling ---------------------------------------------------------
  const refresh = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals()]);
      setTickets(t); setCash(c); setApprovals(a); setOnline(true);
      setSelected(s => s ?? t.find(x => !x.resolved)?.id ?? t[0]?.id ?? null);
    } catch {
      setOnline(false);
    }
  }, []);

  const pullEvents = useCallback(async () => {
    try {
      const { events: fresh, next_since } = await api.events(cursor.current);
      cursor.current = next_since;
      if (fresh.length) setEvents(prev => [...prev, ...fresh]);
    } catch { /* shown by the online dot */ }
  }, []);

  const anyRunning = tickets.some(t => t.running);
  useEffect(() => { refresh(); pullEvents(); }, [refresh, pullEvents]);
  useEffect(() => {
    const a = setInterval(refresh, anyRunning ? 1500 : 3000);
    const b = setInterval(pullEvents, anyRunning ? 800 : 3000);
    return () => { clearInterval(a); clearInterval(b); };
  }, [refresh, pullEvents, anyRunning]);

  useEffect(() => {
    if (selected === null) return;
    api.ticket(selected).then(setDetail).catch(() => setDetail(null));
  }, [selected, tickets]);

  // --- what to show for the selected ticket ------------------------------
  // Only look at events since the last reset, and at the ticket's latest run.
  const sinceReset = useMemo(() => {
    let i = events.length - 1;
    while (i >= 0 && events[i].step !== "reset") i--;
    return events.slice(i + 1);
  }, [events]);

  const runEvents = useMemo(() => {
    const mine = sinceReset.filter(e => e.ticket_id === selected);
    const runs = mine.filter(e => e.step === "run_start" && e.agent === "boss").map(e => e.run_id);
    const latest = runs[runs.length - 1];
    return latest ? mine.filter(e => e.run_id === latest) : [];
  }, [sinceReset, selected]);

  const states = useMemo(() => deriveAgents(runEvents), [runEvents]);
  const resolution = useMemo(() => bossResolution(runEvents), [runEvents]);
  // Join consecutive hops into chains: Boss → Facilities → Accounting.
  const chains = useMemo(() => {
    const out: string[][] = [];
    for (const h of handoffs(runEvents)) {
      const last = out[out.length - 1];
      if (last && last[last.length - 1] === h.from) last.push(h.to);
      else out.push([h.from, h.to]);
    }
    return out;
  }, [runEvents]);
  const ticket = tickets.find(t => t.id === selected) ?? null;
  const pending = approvals.filter(a => a.status === "pending");
  const ticketApprovals = approvals.filter(a => a.ticket_id === selected);

  // --- actions ----------------------------------------------------------
  async function runTeam() {
    if (!selected) return;
    setStarting(true);
    try {
      await api.run(selected);
      flash("ok", `Agent team started on #${selected}`);
      await refresh();
    } catch (e) {
      flash("err", (e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  async function reset() {
    if (!confirm("Reset the working database to the original values? Pending approvals will be cleared.")) return;
    try {
      await api.reset();
      flash("ok", "Database reset: all tickets open, cash back to the original balance.");
      await Promise.all([refresh(), pullEvents()]);
    } catch (e) {
      flash("err", (e as Error).message);
    }
  }

  const afterDecision = async () => { await Promise.all([refresh(), pullEvents()]); };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">CC</span>
          <div>
            <div className="brand-name">Campus Customs</div>
            <div className="brand-sub">Multi-agent ops desk{detail ? ` · shop date ${detail.shop_today}` : ""}</div>
          </div>
        </div>
        <div className="topbar-right">
          <div className={`stat ${pending.length ? "attention" : ""}`}>
            <div className="stat-label">Approvals</div>
            <div className="stat-value">{pending.length ? `${pending.length} waiting` : "All clear"}</div>
          </div>
          <div className="stat">
            <div className="stat-label">Resolved</div>
            <div className="stat-value">{tickets.filter(t => t.resolved).length} / {tickets.length}</div>
          </div>
          <CashTile cash={cash} />
          <div className={`conn ${online ? "on" : online === false ? "off" : ""}`} title={API_BASE}>
            <span className="dot" />{online === false ? "Backend offline" : "Connected"}
          </div>
          <button className="btn ghost light" onClick={reset}>Reset DB</button>
        </div>
      </header>

      {online === false && (
        <div className="banner err">Can't reach the backend at {API_BASE}. Start it from backend/ with <code>uvicorn main:app --reload --port 8000</code>.</div>
      )}
      {notice && <div className={`banner ${notice.kind}`}>{notice.text}</div>}

      <div className="layout">
        <TicketList tickets={tickets} selected={selected} onSelect={setSelected} />

        <main className="col center">
          {ticket && detail ? (
            <section className="panel hero">
              <div className="hero-top">
                <div>
                  <div className="muted small">#{ticket.id} · {ticket.type.replace("_", " ")} · from {ticket.requester}</div>
                  <h1>{ticket.subject}</h1>
                </div>
                <div className="hero-actions">
                  <StatusPill status={ticket.status} running={ticket.running} />
                  <button
                    className="btn primary"
                    disabled={starting || ticket.running || ticket.resolved}
                    onClick={runTeam}
                  >
                    {ticket.resolved ? "✓ Resolved" : ticket.running ? "Agents working…" : runEvents.length ? "Run team again" : "▶ Run agent team"}
                  </button>
                </div>
              </div>
              <div className="facts">
                {detail.sku && <span className="fact"><b>SKU</b> {detail.sku}</span>}
                {detail.size && <span className="fact"><b>Size</b> {detail.size}</span>}
                {detail.qty !== null && <span className="fact"><b>Qty</b> {detail.qty}</span>}
                {detail.lease_id !== null && <span className="fact"><b>Lease</b> {detail.lease_id}</span>}
                {detail.invoice_id !== null && <span className="fact"><b>Invoice</b> {detail.invoice_id}</span>}
                <span className="fact note">“{detail.notes?.split("\n")[0]}”</span>
              </div>
              {chains.length > 0 && (
                <div className="path">
                  <span className="muted small">Handoffs</span>
                  {chains.map((chain, i) => (
                    <span key={i} className="hop">
                      {chain.map((who, j) => (
                        <span key={j} className="hop">
                          {j > 0 && <span className="arrow">→</span>}
                          <span className="hop-chip" style={{ background: AGENT_BY_NAME[who as AgentName]?.color }}>{AGENT_BY_NAME[who as AgentName]?.label}</span>
                        </span>
                      ))}
                    </span>
                  ))}
                </div>
              )}
              {ticket.resolved && (
                <div className="resolved-banner">
                  ✓ Resolved{ticketApprovals.length > 0 && ` · ${ticketApprovals.filter(a => a.status === "approved").length} approved, ${ticketApprovals.filter(a => a.status === "rejected").length} rejected`}
                  {ticketApprovals.filter(a => a.status === "approved").length > 0 &&
                    ` · cash out ${money(ticketApprovals.filter(a => a.status === "approved").reduce((s, a) => s + a.amount, 0))}`}
                </div>
              )}
            </section>
          ) : (
            <section className="panel empty">{online === false ? "Waiting for the backend…" : "Loading tickets…"}</section>
          )}

          <AgentFloor states={states} live={!!ticket?.running} />
          <RunReport resolution={resolution} states={states} ticketResolved={!!ticket?.resolved} />
          <ActivityFeed events={runEvents} live={!!ticket?.running} />
        </main>

        <aside className="col side">
          <Approvals approvals={approvals} cash={cash?.checking ?? null} onChange={afterDecision} />
        </aside>
      </div>
    </div>
  );
}
