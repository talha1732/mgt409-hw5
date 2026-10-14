import type { Ticket } from "../api";

const TYPE_ICON: Record<string, string> = {
  customer_order: "🛍️",
  rent_notice: "🏠",
  price_override: "🏷️",
};

export const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_progress: "Agents working",
  awaiting_approval: "Needs approval",
  resolved: "Resolved",
};

export function StatusPill({ status, running }: { status: string; running?: boolean }) {
  const s = running ? "running" : status;
  return (
    <span className={`pill pill-${s}`}>
      <span className="dot" />
      {running ? "Running" : STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function TicketList({
  tickets, selected, onSelect,
}: { tickets: Ticket[]; selected: number | null; onSelect: (id: number) => void }) {
  const done = tickets.filter(t => t.resolved).length;
  return (
    <aside className="col tickets">
      <div className="col-head">
        <h2>Tickets</h2>
        <span className="muted small">{done}/{tickets.length} resolved</span>
      </div>
      <div className="progress"><span style={{ width: `${tickets.length ? (done / tickets.length) * 100 : 0}%` }} /></div>
      {tickets.map(t => (
        <button
          key={t.id}
          className={`ticket-card ${selected === t.id ? "selected" : ""} ${t.resolved ? "is-resolved" : ""}`}
          onClick={() => onSelect(t.id)}
        >
          <div className="tc-top">
            <span className="tc-icon" aria-hidden>{t.resolved ? "✓" : TYPE_ICON[t.type] ?? "📄"}</span>
            <span className="tc-id">#{t.id}</span>
            <StatusPill status={t.status} running={t.running} />
          </div>
          <div className="tc-subject">{t.subject}</div>
          <div className="tc-meta">{t.requester} · {t.type.replace("_", " ")}</div>
          {t.pending_approvals > 0 && (
            <div className="tc-flag">💵 {t.pending_approvals} payment{t.pending_approvals > 1 ? "s" : ""} waiting for you</div>
          )}
        </button>
      ))}
    </aside>
  );
}
