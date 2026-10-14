import { useState } from "react";
import { api, money, type Approval } from "../api";
import { colorOf, label } from "../agents";

const KIND: Record<string, { icon: string; title: (a: Approval) => string }> = {
  invoice: { icon: "🧾", title: a => `Pay invoice ${a.invoice_id}` },
  rent: { icon: "🏠", title: a => `Pay rent · lease ${a.lease_id}` },
  purchase_order: { icon: "📦", title: a => `Purchase ${a.qty} × ${a.sku} ${a.size}` },
};

function ApprovalCard({
  a, all, cash, approver, onDone,
}: { a: Approval; all: Approval[]; cash: number | null; approver: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qty, setQty] = useState<number>(a.qty ?? 0);
  const blocker = all.find(b => b.id === a.depends_on && b.status === "pending");
  const unitCost = a.kind === "purchase_order" && a.qty ? a.amount / a.qty : 0;
  const amount = a.kind === "purchase_order" ? +(unitCost * qty).toFixed(2) : a.amount;
  const after = cash === null ? null : cash - amount;
  const short = after !== null && after < 0;

  async function act(kind: "approve" | "reject") {
    if (!approver.trim()) { setError("Enter your name above first, a human has to sign off."); return; }
    setBusy(true); setError(null);
    try {
      if (kind === "approve") await api.approve(a.id, approver.trim(), a.kind === "purchase_order" && qty !== a.qty ? qty : undefined);
      else await api.reject(a.id, approver.trim(), "Declined on the desk");
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`approval ${blocker ? "blocked" : ""} ${short ? "short" : ""}`}>
      <div className="ap-top">
        <span className="ap-icon">{KIND[a.kind].icon}</span>
        <div className="ap-title">
          <div>{KIND[a.kind].title({ ...a, qty })}</div>
          <div className="muted small">#{a.id} · ticket {a.ticket_id} · prepared by{" "}
            <span className="who" style={{ color: colorOf(a.requested_by ?? "system") }}>{label(a.requested_by ?? "system")}</span>
          </div>
        </div>
        <div className="ap-amount">{money(amount)}</div>
      </div>
      <div className="ap-reason">{a.reason}</div>
      {a.kind === "purchase_order" && a.qty && a.qty > 1 && (
        <label className="ap-qty small">
          Qty
          <input type="range" min={1} max={a.qty} value={qty} onChange={e => setQty(+e.target.value)} />
          <b>{qty}</b> / {a.qty} at {money(unitCost)}
        </label>
      )}
      {after !== null && (
        <div className={`ap-after small ${short ? "bad" : ""}`}>
          Checking after: <b>{money(after)}</b>{short && " · not enough cash, the pay tool will refuse"}
        </div>
      )}
      {blocker && <div className="ap-lock small">🔒 Approve #{blocker.id} ({KIND[blocker.kind].title(blocker)}) first, the vendor won't ship while it's unpaid.</div>}
      {error && <div className="ap-error small">{error}</div>}
      <div className="ap-actions">
        <button className="btn ghost" disabled={busy} onClick={() => act("reject")}>Reject</button>
        <button className="btn approve" disabled={busy || !!blocker || short} onClick={() => act("approve")}>
          {busy ? "Working…" : `Approve ${money(amount)}`}
        </button>
      </div>
    </div>
  );
}

export function Approvals({
  approvals, cash, onChange,
}: { approvals: Approval[]; cash: number | null; onChange: () => void }) {
  const [approver, setApprover] = useState(() => localStorage.getItem("cc-approver") ?? "");
  const pending = approvals.filter(a => a.status === "pending");
  const decided = approvals.filter(a => a.status !== "pending").slice().reverse();

  return (
    <section className={`panel approvals-panel ${pending.length ? "has-pending" : ""}`}>
      <div className="panel-head">
        <h3>Needs your approval {pending.length > 0 && <span className="count">{pending.length}</span>}</h3>
      </div>
      <p className="muted small rule">Agents only <b>prepare</b> payments. Money moves only when a person approves here.</p>
      <label className="approver small">
        Approving as
        <input
          placeholder="Your name"
          value={approver}
          onChange={e => { setApprover(e.target.value); localStorage.setItem("cc-approver", e.target.value); }}
        />
      </label>
      {pending.length === 0 && <div className="empty small">Nothing waiting. Payments the agents prepare will show up here.</div>}
      {pending.map(a => (
        <ApprovalCard key={a.id} a={a} all={approvals} cash={cash} approver={approver} onDone={onChange} />
      ))}
      {decided.length > 0 && (
        <div className="ledger">
          <div className="ledger-head small muted">Decided</div>
          {decided.map(a => (
            <div key={a.id} className={`ledger-row ${a.status}`}>
              <span>{a.status === "approved" ? "✅" : "✖"} #{a.id} {KIND[a.kind].title(a)}</span>
              <span>{a.status === "approved" ? `−${money(a.amount)}` : "no charge"}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
