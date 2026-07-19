#!/usr/bin/env python3
"""The Night Shift — brief it before bed, judge it over coffee.

A persisted, hand-editable, diffable call sheet (`night-shift-queue.json`)
of firing orders the booth works one row at a time, strictly serial,
through the SAME fail-closed guard every other station uses. This is
containment, not throughput: the guard exists because bypassing it
OOM-killed the WSL VM twice on 2026-07-09 — an overnight queue that
weakened it to go faster would reopen that incident unattended, with
nobody there to catch it. The Night Shift never gets its own GPU lock.

The row schema is workshop-wide from day one — `subject × K variants ×
job_type` is the grammar The Docket will one day generalize across every
room — but this arc validates exactly ONE job_type: "kiln". The field is
real and enforced even though only one value is legal yet; a schema that
had to be widened later would not be a pilot, it would be a rewrite.

`takes_done` is the resume cursor: a booth restart mid-row resumes from
the row's first unfinished take — never the whole queue, never a
duplicate take. Row failure is infrastructure-only (the kiln going cold);
a shredded mesh parks flagged and the shift keeps working.

Stdlib only, same philosophy as the rest of the booth. (Blueprint note:
the experiment log names this file night-shift.py; Python cannot import a
hyphen, so the module answers to night_shift.py — resolved at build time,
as the log allows.)
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

QUEUE_FILE = Path(__file__).resolve().parent / "night-shift-queue.json"
VALID_JOB_TYPES = ("kiln",)   # The Docket widens this list, not this arc
ROW_STATUSES = ("queued", "firing", "done", "failed")


class CallSheetError(ValueError):
    """A row that cannot go on tonight's call sheet, with the reason named."""


# ------------------------------------------------------------- the call sheet

def validate_row(row):
    """Normalize and validate one order. Returns the normalized row dict.

    Both K grammars are legal: a single subject phrase (K seed-varied takes
    of one subject) or a list of K phrases (K different props in one row).
    """
    if not isinstance(row, dict):
        raise CallSheetError("An order is a JSON object — this row is not one.")
    subject = row.get("subject")
    if isinstance(subject, str):
        subject = subject.strip()
        if not subject:
            raise CallSheetError("An order needs a subject — the kiln fires nothing from an empty phrase.")
        subjects = None
    elif isinstance(subject, list):
        subjects = [str(s).strip() for s in subject]
        if not subjects or any(not s for s in subjects):
            raise CallSheetError("A subject list must hold at least one non-empty phrase per take.")
    else:
        raise CallSheetError("An order needs a subject — one phrase, or a list of phrases.")

    job_type = row.get("job_type", "kiln")
    if job_type not in VALID_JOB_TYPES:
        raise CallSheetError(
            f"The call sheet knows no '{job_type}' job — tonight the only "
            f"stagehand on shift is {', '.join(repr(t) for t in VALID_JOB_TYPES)}. "
            "(The Docket may widen the roster; this shift does not.)"
        )

    try:
        k = int(row.get("variant_count", len(subjects) if subjects else 1))
    except (TypeError, ValueError):
        raise CallSheetError("variant_count must be a whole number of takes.") from None
    if k < 1:
        raise CallSheetError("variant_count must be at least 1 — a zero-take order is a blank line.")
    if subjects is not None and len(subjects) != k:
        raise CallSheetError(
            f"The row lists {len(subjects)} subject phrases but asks for "
            f"variant_count {k} — either grammar is fine, but they must agree."
        )

    status = row.get("status", "queued")
    if status not in ROW_STATUSES:
        raise CallSheetError(f"'{status}' is not a state a row can hold — one of {ROW_STATUSES}.")

    return {
        "id": row.get("id") or f"row-{uuid4().hex[:8]}",
        "subject": subjects if subjects is not None else subject,
        "variant_count": k,
        "job_type": job_type,
        "octree": int(row.get("octree", 128)),
        "threshold": float(row.get("threshold", 0.5)),
        "two_sided": bool(row.get("two_sided", False)),
        "seed": row.get("seed"),          # base seed; take i fires at seed+i
        "status": status,
        "takes_done": int(row.get("takes_done", 0)),
        "reason": row.get("reason"),      # voiced, set only on failure
        "added_at": row.get("added_at") or datetime.now().isoformat(timespec="seconds"),
    }


def load_queue(path=None):
    path = Path(path or QUEUE_FILE)
    try:
        rows = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return rows if isinstance(rows, list) else []


def save_queue(rows, path=None):
    """Atomic write — a mid-save booth death never leaves half a call sheet."""
    path = Path(path or QUEUE_FILE)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=1))
    os.replace(tmp, path)


def add_row(row, path=None):
    normalized = validate_row(row)
    rows = load_queue(path)
    rows.append(normalized)
    save_queue(rows, path)
    return normalized


def remove_row(row_id, path=None):
    rows = load_queue(path)
    kept = [r for r in rows if r.get("id") != row_id]
    if len(kept) == len(rows):
        raise CallSheetError(f"No order '{row_id}' stands on the call sheet.")
    save_queue(kept, path)


def reorder_row(row_id, direction, path=None):
    """Move an order up or down one slot — legal mid-shift; the runner picks
    the new order up at the next row boundary, no restart needed."""
    rows = load_queue(path)
    idx = next((i for i, r in enumerate(rows) if r.get("id") == row_id), None)
    if idx is None:
        raise CallSheetError(f"No order '{row_id}' stands on the call sheet.")
    swap = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap < len(rows):
        rows[idx], rows[swap] = rows[swap], rows[idx]
        save_queue(rows, path)


def _update_row(row_id, updates, path=None):
    """Re-read, patch by id, re-save — so a panel edit mid-shift is never
    clobbered by the runner's own bookkeeping."""
    rows = load_queue(path)
    for r in rows:
        if r.get("id") == row_id:
            r.update(updates)
            break
    save_queue(rows, path)


def has_firing_row(path=None):
    """True when a shift died mid-row — the booth resumes it on start."""
    return any(r.get("status") == "firing" for r in load_queue(path))


# ------------------------------------------------------------------ the shift

_shift = {
    "running": False,
    "row_id": None,
    "subject": None,
    "started": None,
    "stop": threading.Event(),
    "thread": None,
}
_start_gate = threading.Lock()  # process bookkeeping only — NOT a GPU lock;
                                # the GPU is guarded by the shared clear_the_set


def shift_status():
    return {
        "running": _shift["running"],
        "row_id": _shift["row_id"],
        "subject": _shift["subject"],
        "started": _shift["started"],
    }


def start_shift(fire_take, stations_clear, log=None, path=None, poll_s=3.0):
    """Put the shift on the floor. `fire_take(row, take_index, subject, seed)`
    runs one full firing chain and parks the candidate; `stations_clear()`
    answers whether the floor is free (no Stage/Foley take live, no full UI
    holding the GPU). The runner is one thread working one row at a time —
    serialized IS the shift."""
    with _start_gate:
        if _shift["running"]:
            return False, "The shift is already on the floor — one crew a night."
        _shift.update({
            "running": True, "row_id": None, "subject": None,
            "started": datetime.now().isoformat(timespec="seconds"),
        })
        _shift["stop"].clear()
        t = threading.Thread(
            target=_run_shift,
            args=(fire_take, stations_clear, log or (lambda _m: None), path, poll_s),
            daemon=True,
        )
        _shift["thread"] = t
        t.start()
        return True, "The Night Shift is on the floor."


def stop_shift():
    """Ring the bell. The current take finishes (a firing is never killed
    mid-mesh); the row keeps its takes_done cursor and resumes next shift."""
    _shift["stop"].set()
    return shift_status()


def _next_row(rows):
    """First row still owed work, in call-sheet order. A 'firing' row is a
    resumption (the cursor says where); 'queued' rows follow."""
    return next((r for r in rows if r.get("status") in ("firing", "queued")), None)


def _run_shift(fire_take, stations_clear, log, path, poll_s):
    stop = _shift["stop"]
    log("the Night Shift clocks in — reading the call sheet")
    try:
        while not stop.is_set():
            rows = load_queue(path)
            raw = _next_row(rows)
            if raw is None:
                log("the call sheet is worked through — the shift clocks out")
                break
            done = _run_row(raw, fire_take, stations_clear, log, path, poll_s, stop)
            if not done:
                break  # stopped mid-row (cursor persisted) or the kiln went cold
    finally:
        _shift.update({"running": False, "row_id": None, "subject": None})


def _run_row(raw, fire_take, stations_clear, log, path, poll_s, stop):
    """Work one order to completion. Returns True when the shift may move to
    the next row; False when it must clock out (stop rung, or the kiln went
    cold — a cold kiln fails every row after it identically, so the shift
    ends and the Scientist restarts it once the floor is warm again)."""
    try:
        row = validate_row(raw)
    except CallSheetError as e:
        _update_row(raw.get("id", "?"), {"status": "failed", "reason": str(e)}, path)
        log(f"an order was refused at the door: {e}")
        return True  # a bad row never sinks the sheet

    k = row["variant_count"]
    subjects = row["subject"] if isinstance(row["subject"], list) else [row["subject"]] * k
    base_seed = row["seed"] if row["seed"] is not None else int(time.time()) % 2 ** 31
    row_id = row["id"]

    for i in range(row["takes_done"], k):
        # Containment first: the floor must be clear BEFORE the row lights.
        waited = False
        while not stations_clear():
            if not waited:
                log("the floor is busy — the shift waits at the door "
                    "(the row stays queued until the guard releases)")
                waited = True
            if stop.wait(poll_s):
                return False
        if stop.is_set():
            return False
        if row["status"] != "firing" or i == row["takes_done"]:
            _update_row(row_id, {"status": "firing"}, path)
            row["status"] = "firing"
        _shift.update({"row_id": row_id, "subject": subjects[i]})
        take_seed = (base_seed + i) % 2 ** 31
        log(f"row {row_id} — take {i + 1}/{k}: '{subjects[i]}' (seed {take_seed})")
        try:
            fire_take(row, i, subjects[i], take_seed)
        except Exception as e:  # infrastructure, not craft — shred parks, never raises
            reason = str(e) or "the kiln went cold mid-firing"
            _update_row(row_id, {"status": "failed", "reason": reason}, path)
            log(f"row {row_id} failed: {reason}")
            log("the shift clocks out early — a cold kiln fails every order the same way")
            return False
        _update_row(row_id, {"takes_done": i + 1}, path)

    _update_row(row_id, {"status": "done"}, path)
    log(f"row {row_id} is done — {k} take{'s' if k != 1 else ''} parked on the Curing Rack")
    return True
