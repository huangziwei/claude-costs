#!/usr/bin/env python3
"""Stamp the session exit reason in ~/.claude/session-costs.csv.

Called by the SessionEnd hook.  The cost data is already maintained by the
status-line command on every tick; this hook only adds the exit reason.
"""

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

CSV_PATH = Path.home() / ".claude" / "session-costs.csv"
CSV_FIELDS = [
    "timestamp",
    "session_id",
    "project",
    "model",
    "cost_usd",
    "reason",
]


def main() -> None:
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return

    session_id = hook_input.get("session_id", "unknown")
    reason = hook_input.get("reason", "unknown")

    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return

    rows: list[dict] = []
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    found = False
    for row in rows:
        if row.get("session_id") == session_id:
            row["reason"] = reason
            found = True
            break

    if not found:
        return

    fd, tmp = tempfile.mkstemp(dir=CSV_PATH.parent, suffix=".csv")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
        os.replace(tmp, CSV_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    main()
