// Thin client for the FastAPI backend (backend/main.py).

export const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";
export type Actor = AgentName | "human" | "system";
export type TicketStatus = "open" | "in_progress" | "awaiting_approval" | "resolved";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  status: TicketStatus;
  created_at: string;
  resolved: boolean;
  running: boolean;
  pending_approvals: number;
}

export interface TicketDetail extends Ticket {
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  notes: string | null;
  shop_today: string;
}

export interface AuditEvent {
  run_id: string;
  ticket_id: number | null;
  seq: number;
  timestamp: string;
  agent: Actor;
  chain: string[];
  step: string;
  detail: Record<string, any>;
  usage: Record<string, number> | null;
}

export interface Approval {
  id: number;
  ticket_id: number;
  run_id: string;
  kind: "invoice" | "rent" | "purchase_order";
  amount: number;
  reason: string;
  invoice_id: number | null;
  lease_id: number | null;
  vendor_id: number | null;
  sku: string | null;
  size: string | null;
  qty: number | null;
  requested_by: AgentName | null;
  status: "pending" | "approved" | "rejected";
  depends_on: number | null;
  decided_at: string | null;
  approved_by: string | null;
  result: Record<string, any> | null;
  last_error: Record<string, any> | null;
}

export interface Cash {
  checking: number;
  as_of: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const msg =
      typeof detail === "string" ? detail
      : detail?.error ? `${detail.error}${detail.short_by ? ` (short by $${detail.short_by.toFixed(2)})` : ""}`
      : Array.isArray(detail) ? detail.map((d: any) => d.msg).join("; ")
      : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return body as T;
}

export const api = {
  tickets: () => request<Ticket[]>("/tickets"),
  ticket: (id: number) => request<TicketDetail>(`/tickets/${id}`),
  run: (id: number) => request<{ run_id: string }>(`/tickets/${id}/run`, { method: "POST" }),
  events: (since: number) =>
    request<{ events: AuditEvent[]; next_since: number }>(`/events?since=${since}&limit=2000`),
  approvals: () => request<Approval[]>("/approvals"),
  approve: (id: number, approved_by: string, qty?: number) =>
    request<{ ticket_resolved: boolean }>(`/approvals/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by, ...(qty ? { qty } : {}) }),
    }),
  reject: (id: number, rejected_by: string, reason: string) =>
    request<{ ticket_resolved: boolean }>(`/approvals/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ rejected_by, reason }),
    }),
  cash: () => request<Cash>("/cash"),
  reset: () => request<{ reset: boolean }>("/reset", { method: "POST" }),
};

export const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD" });
