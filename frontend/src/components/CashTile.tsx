import { useEffect, useRef, useState } from "react";
import { money, type Cash } from "../api";

/** Checking balance. Flashes the change whenever an approval moves money. */
export function CashTile({ cash }: { cash: Cash | null }) {
  const prev = useRef<number | null>(null);
  const [delta, setDelta] = useState<number | null>(null);

  useEffect(() => {
    if (!cash) return;
    if (prev.current !== null && prev.current !== cash.checking) {
      setDelta(cash.checking - prev.current);
      const t = setTimeout(() => setDelta(null), 4500);
      prev.current = cash.checking;
      return () => clearTimeout(t);
    }
    prev.current = cash.checking;
  }, [cash]);

  return (
    <div className={`cash-tile ${delta !== null ? (delta < 0 ? "down" : "up") : ""}`}>
      <div className="cash-label">Checking</div>
      <div className="cash-value">{cash ? money(cash.checking) : "—"}</div>
      {delta !== null && <div className="cash-delta">{delta < 0 ? "−" : "+"}{money(Math.abs(delta))}</div>}
    </div>
  );
}
