"""Append-only audit trail for agent runs: output/audit_trail.json."""

from __future__ import annotations

import fcntl
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import AuditEntry

AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
_LOCK = threading.Lock()


class AuditLog:
    """Writes each step as it happens, so a crashed or limited run still
    leaves a trail. Earlier runs in the file are never removed."""

    def __init__(self, run_id: str, ticket_id: int | None, path: Path = AUDIT_PATH):
        self.run_id = run_id
        self.ticket_id = ticket_id
        self.path = path
        self._seq = 0

    def log(
        self,
        agent: str,
        chain: list[str],
        step: str,
        detail: dict[str, Any] | None = None,
        usage: dict[str, int] | None = None,
    ) -> AuditEntry:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Thread lock for one process, file lock for several (e.g. CLI + server).
        with _LOCK, open(self.path.with_suffix(".lock"), "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            history = read_audit(self.path)
            if self._seq == 0:
                # Continue numbering if this run already has entries (e.g. a
                # human approval logged after the agents finished).
                self._seq = max(
                    (e.get("seq", 0) for e in history if e.get("run_id") == self.run_id), default=0
                )
            self._seq += 1
            entry = AuditEntry(
                run_id=self.run_id,
                ticket_id=self.ticket_id,
                seq=self._seq,
                timestamp=datetime.now(timezone.utc),
                agent=agent,
                chain=list(chain),
                step=step,
                detail=detail or {},
                usage=usage,
            )
            history.append(entry.model_dump(mode="json"))
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self.path)
        return entry


def read_audit(path: Path = AUDIT_PATH) -> list[dict]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Never overwrite a file we can't parse; keep it aside and start fresh.
        path.rename(path.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}.json"))
        return []
    return loaded if isinstance(loaded, list) else [loaded]
