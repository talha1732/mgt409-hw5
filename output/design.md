# Campus Customs Ops Desk: dashboard design

The board is in `frontend/` (React + Vite + TypeScript). It talks to the FastAPI backend at http://localhost:8000.

To run it:
1. Start the backend from `backend/`: `uvicorn main:app --reload --port 8000`.
2. Start the board from `frontend/`: `npm run dev`.
3. Open http://localhost:5173.

## Why this layout

The board is built like a real operations desk: **work in on the left, the team in the middle, decisions on the right.** You read it left to right, the same order a ticket moves through the shop.

| Area | What's in it | Why it's there |
|---|---|---|
| **Top bar** | The shop's date, an **Approvals** counter, a **Resolved** counter (x / 3), the **Checking** balance, a backend connection light, and **Reset DB** | The four numbers a manager checks first are visible on every screen, without scrolling. |
| **Left: ticket cards** | One card for each ticket with an icon, id, subject, requester and status pill, plus a progress bar for how many are resolved | It's the inbox. You can see at a glance what's open, what's running, what's stuck on money, and what's done. Click a card to open it. |
| **Center: the selected ticket** | The ticket's header and **Run agent team** button, then the **Agent floor**, the **Run report** and the **Live activity** feed | This is where the agents work, so it gets the most room. |
| **Right: Needs your approval** | Prepared payments waiting for a human, and a "Decided" ledger below them | The human's job sits in its own column, so a payment waiting for approval never gets lost in the agent chatter. |

The ticket list and approval column stay in view while the center scrolls. On smaller screens the approval column moves under the center, and on a phone everything stacks.

## How the agents are shown

- **Each agent has one color, used everywhere.** Boss is navy, Inventory green, Accounting amber-brown, Facilities purple, Customer Service raspberry. The same color appears on the agent's card, its badge in the activity feed, its handoff chips and its row in the run report, so you can follow one agent down the page. The colors match `output/desk_tickets.html`, so the plan and the live board read the same way.
- **The Agent floor shows all five agents on every ticket**, even ones the Boss doesn't call. An agent that isn't needed is greyed out and labeled "Not on this ticket". This makes it obvious that the Boss chose a small team (3 of 5 on rent) rather than calling everyone.
- **Each card shows what the agent is doing right now**:
  - A status line: *Thinking*, *Using a tool*, *Waiting on a teammate* or *Done ✓*. Working agents get a pulsing dot and a glowing outline in their color.
  - A **speech bubble** with the agent's latest words. When it calls a tool, the bubble shows the actual call, e.g. `check_rent_due(lease_id=1)`, in code font.
  - **Tool chips** for every MCP tool it used this run, **handoff chips** (→ Accounting) for each teammate it delegated to, and its token count.
- **Handoff chain:** under the ticket title, handoffs read as a chain, e.g. **Boss → Facilities → Accounting**. You see who delegated to whom without reading the log.
- **Live activity** is the timeline under all of this: who acted, a symbol for the kind of step (▶ start, ⚙ tool call, → handoff, ✓ finished, 💵 queued for approval, ✅ approved), and the text. Tool results are hidden by default to keep it readable; tick a box to show them. Human approvals show in green and refusals in red, in the same timeline as the agents, so the whole story of a ticket is in one place.
- All of this is rebuilt from the backend's append-only audit trail (`/events`), so the board shows exactly what was logged. The board polls more often while a run is in progress (about every 1 second) so it updates live.

## How resolved tickets and payment approvals show up

**Ticket status uses the same four colors on every pill:**

| Color | Status |
|---|---|
| Grey | Open |
| Blue, pulsing | Running / Agents working |
| Amber | Needs approval |
| Green | Resolved |

- An amber line on the ticket card, "💵 1 payment waiting for you", tells you which ticket is stuck on money.
- **When a ticket is resolved:**
  - its card gets a green left edge and a ✓, and the progress bar fills
  - the Run button turns into a disabled **✓ Resolved**
  - a green banner sums up the human decisions, e.g. *"✓ Resolved · 1 approved, 0 rejected · cash out $2,400.00"*
  - the run report pill changes to *"Resolved after human decision"*
- **The approval panel** has an amber outline and a count while anything is waiting. Each prepared payment is a card showing:
  - what it is (🧾 invoice, 🏠 rent, 📦 purchase order), the amount, and which agent prepared it
  - the agent's reason
  - **"Checking after: $X"**, so you see the effect before you click. If cash would go negative, it turns red, says the pay tool will refuse, and the Approve button is disabled.
  - a **🔒 lock** if the payment depends on another one, e.g. the purchase order is locked until invoice 501 is paid, because the vendor won't ship while it's unpaid
  - a **quantity slider** on purchase orders, so a human can buy fewer when cash is tight (useful for ticket 103)
  - **Approve** (green, shows the amount) and **Reject**
- **Only a named human can approve.** The panel asks "Approving as: your name" and won't send anything without it. The backend also refuses blank or agent names. A note says plainly: *Agents only prepare payments. Money moves only when a person approves here.*
- **Cash** in the top bar updates right after an approval. It flashes red with the change (e.g. **−$2,400.00**) for a few seconds, and the "Decided" ledger keeps a running list of what was paid.

## What makes it easy to use

- **One click per step:** pick a ticket, run the team, approve or reject. Everything else is information.
- **Status by color, shape and words together:** a colored pill always has a text label, and resolved tickets also get a ✓. The board doesn't rely on color alone.
- **Facts on the ticket header:** SKU, size, qty, lease and invoice are pulled from the database, so you don't have to open the database to know what the ticket is about.
- **A Run report when the team finishes:**
  - the Boss's outcome
  - **one line for what each agent did**, plus the tools it used
  - which agents weren't needed
  - next steps for you
  - the **customer draft** in an email-style card marked "stays on the board, never sent"
- **Safe by default:**
  - Approve is disabled when a payment is locked or there isn't enough cash, and errors from the pay tool appear right on the card.
  - Reset asks for confirmation.
  - You can't run a ticket twice at the same time, and resolved tickets can't be re-run.
- **Connection awareness:** a green or red light shows whether the backend is reachable. If it isn't, a banner tells you the exact command to start it.
- **Calm visual style:**
  - a light grey canvas with white cards, a deep Yale navy header, rounded corners and soft shadows
  - numbers that line up so money is easy to scan
  - motion only where it means something: pulsing for "working", a pop for "cash just changed"

## Tested

Driven in headless Chrome against the live backend:
1. Reset.
2. Selected ticket 102 and ran the team. The Boss card was live at once, then Boss → Facilities → Accounting worked, with tool chips `check_rent_due` and `get_cash_balance`.
3. The ticket moved to *Needs approval* and the $2,400 rent card appeared, showing "Checking after: $1,000.00".
4. Approving without a name was blocked. Approving as a named human moved checking from **$3,400.00 to $1,000.00** with a −$2,400.00 flash.
5. The ticket turned **Resolved** (green card, 1/3 resolved), and the approval appeared in the activity feed.
6. No browser console errors. The database was reset afterwards.
