"""Investigation case log and the Insights MVP.

Every case keeps created / started / reviewed / completed / due timestamps, and every status
change is appended as an immutable, timestamped event. Insights are computed from those
events only, so each number on the dashboard can be traced back to logged handoffs:

* exception frequency by location (and by exception type)
* detection-to-review time (detected_at -> first human action)
* investigation cycle time, average AND median (created_at -> completed_at)
* throughput (cases closed per week)
* unresolved and overdue cases (review or close SLA breached)
* backlog burndown for a scoped window (open cases per day vs an ideal line)

`backfill_from_labels` turns labelled exception episodes in the synthetic telemetry into
historical cases. Detection times come from the labels; human handling times are drawn from a
seeded distribution and every such case is marked `synthetic=True`, so the API always reports
how many cases are live and how many are simulated.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import statistics
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from . import thresholds as TH

STATES = ("Open", "In progress", "Under review", "Closed")
HUMAN_STATES = ("In progress", "Under review", "Closed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat(timespec="seconds") if d else None


def _parse(s: str | datetime | None) -> datetime | None:
    if s is None or s == "":
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@dataclass
class CaseEvent:
    case_id: str
    seq: int
    ts: str
    event: str  # created | assigned | review_started | status_changed | note | closed
    from_state: str | None
    to_state: str | None
    actor: str
    note: str = ""
    prev_hash: str = ""
    hash: str = ""

    def seal(self) -> "CaseEvent":
        body = {k: v for k, v in asdict(self).items() if k != "hash"}
        self.hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return self


@dataclass
class Case:
    case_id: str
    location_id: str
    kind: str
    priority: str
    detected_at: str
    created_at: str
    review_due_at: str
    close_due_at: str
    batch_code: str = ""
    assignee: str = ""
    state: str = "Open"
    started_at: str | None = None      # first human action (assign / acknowledge)
    reviewed_at: str | None = None     # moved to Under review
    completed_at: str | None = None    # closed
    synthetic: bool = False
    thresholds_version: str = ""
    events: list[CaseEvent] = field(default_factory=list)

    def public(self, with_events: bool = False) -> dict:
        d = asdict(self)
        if not with_events:
            d.pop("events")
        return d


class CaseStore:
    """Thread-safe, append-only case log. Optional JSONL persistence via $CASE_EVENTS_PATH."""

    def __init__(self, events_path: str | None = None, cfg: dict | None = None):
        self.cfg = cfg or TH.load()
        self.cases: dict[str, Case] = {}
        self._lock = threading.Lock()
        self.events_path = events_path if events_path is not None else os.getenv("CASE_EVENTS_PATH")

    # --- writes -------------------------------------------------------------------------------
    def _append(self, case: Case, event: str, actor: str, to_state: str | None, note: str, ts: datetime) -> CaseEvent:
        prev = case.events[-1].hash if case.events else ""
        ev = CaseEvent(case.case_id, len(case.events) + 1, _iso(ts), event, case.state if case.events else None,
                       to_state, actor, note, prev).seal()
        case.events.append(ev)
        if self.events_path:
            Path(self.events_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(ev)) + "\n")
        return ev

    def create(self, case_id: str, location_id: str, kind: str, priority: str = "High", *,
               detected_at: str | datetime | None = None, created_at: str | datetime | None = None,
               batch_code: str = "", actor: str = "detector", synthetic: bool = False) -> Case:
        with self._lock:
            if case_id in self.cases:
                return self.cases[case_id]
            created = _parse(created_at) or _now()
            detected = _parse(detected_at) or created
            sla = self.cfg["sla"]
            case = Case(
                case_id=case_id, location_id=location_id, kind=kind, priority=priority,
                detected_at=_iso(detected), created_at=_iso(created),
                review_due_at=_iso(created + timedelta(hours=sla["review_due_hours"].get(priority, 12))),
                close_due_at=_iso(created + timedelta(hours=sla["close_due_hours"].get(priority, 48))),
                batch_code=batch_code, synthetic=synthetic, thresholds_version=self.cfg["version"],
            )
            self.cases[case_id] = case
            self._append(case, "created", actor, "Open", f"{kind} at {location_id}", created)
            return case

    def transition(self, case_id: str, to_state: str, actor: str, note: str = "",
                   ts: str | datetime | None = None, assignee: str | None = None) -> Case:
        if to_state not in STATES:
            raise ValueError(f"unknown state {to_state!r}")
        with self._lock:
            case = self.cases[case_id]
            if case.state == "Closed" and to_state != "Closed":
                raise ValueError(f"{case_id} is closed; reopen by creating a new case")
            when = _parse(ts) or _now()
            if assignee:
                case.assignee = assignee
            event = "assigned" if assignee else ("closed" if to_state == "Closed" else "status_changed")
            self._append(case, event, actor, to_state, note, when)
            if to_state in HUMAN_STATES and case.started_at is None:
                case.started_at = _iso(when)
            if to_state in ("Under review", "Closed") and case.reviewed_at is None:
                case.reviewed_at = _iso(when)
            if to_state == "Closed":
                case.completed_at = _iso(when)
            case.state = to_state
            return case

    def note(self, case_id: str, actor: str, note: str, ts: str | datetime | None = None) -> CaseEvent:
        with self._lock:
            case = self.cases[case_id]
            return self._append(case, "note", actor, case.state, note, _parse(ts) or _now())

    # --- reads --------------------------------------------------------------------------------
    def verify_chain(self, case_id: str) -> bool:
        """True when every event hash matches its body and links to the previous event."""
        prev = ""
        for ev in self.cases[case_id].events:
            body = {k: v for k, v in asdict(ev).items() if k != "hash"}
            if ev.prev_hash != prev or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != ev.hash:
                return False
            prev = ev.hash
        return True

    def all(self) -> list[Case]:
        return list(self.cases.values())


# --- Insights -----------------------------------------------------------------------------------
def _hours(a: str | None, b: str | None) -> float | None:
    da, db = _parse(a), _parse(b)
    return (db - da).total_seconds() / 3600 if da and db else None


def _stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0, "avg_h": None, "median_h": None, "p90_h": None}
    s = sorted(xs)
    p90 = s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]
    return {"n": len(xs), "avg_h": round(statistics.fmean(xs), 2), "median_h": round(statistics.median(xs), 2),
            "p90_h": round(p90, 2)}


def insights(cases: Iterable[Case], now: datetime | None = None, window_days: int = 30,
             scope_start: datetime | None = None) -> dict:
    now = _parse(now) or _now()
    start = now - timedelta(days=window_days)
    cs = [c for c in cases if _parse(c.created_at) >= start or c.state != "Closed"]

    freq: dict[str, dict[str, int]] = {}
    for c in cs:
        if _parse(c.detected_at) >= start:
            freq.setdefault(c.location_id, {}).setdefault(c.kind, 0)
            freq[c.location_id][c.kind] += 1
    for loc, kinds in freq.items():
        kinds["total"] = sum(v for k, v in kinds.items() if k != "total")

    d2r = [h for c in cs if (h := _hours(c.detected_at, c.started_at)) is not None]
    cycle = [h for c in cs if c.completed_at and (h := _hours(c.created_at, c.completed_at)) is not None]

    weeks: dict[str, int] = {}
    for c in cs:
        if c.completed_at and _parse(c.completed_at) >= start:
            wk = _parse(c.completed_at).strftime("%G-W%V")
            weeks[wk] = weeks.get(wk, 0) + 1

    unresolved = [c for c in cs if c.state != "Closed"]
    overdue = []
    for c in unresolved:
        reasons = []
        if c.started_at is None and _parse(c.review_due_at) < now:
            reasons.append("review_overdue")
        if _parse(c.close_due_at) < now:
            reasons.append("close_overdue")
        if reasons:
            overdue.append({"case_id": c.case_id, "location_id": c.location_id, "kind": c.kind,
                            "priority": c.priority, "age_h": round(_hours(c.created_at, _iso(now)), 1),
                            "reasons": reasons})

    # burndown over the scoped window: cases in scope = created on/after scope_start
    s0 = _parse(scope_start) or (now - timedelta(days=min(window_days, 14)))
    scoped = [c for c in cs if _parse(c.created_at) >= s0]
    days = max(1, (now.date() - s0.date()).days)
    total = len(scoped)
    burndown = []
    for i in range(days + 1):
        day_end = datetime.combine(s0.date() + timedelta(days=i), datetime.max.time(), tzinfo=timezone.utc)
        created = sum(1 for c in scoped if _parse(c.created_at) <= day_end)
        closed = sum(1 for c in scoped if c.completed_at and _parse(c.completed_at) <= day_end)
        burndown.append({"date": (s0.date() + timedelta(days=i)).isoformat(), "open": created - closed,
                         "created_to_date": created, "closed_to_date": closed,
                         "ideal_remaining": round(total * (1 - i / days), 1)})

    live = sum(1 for c in cs if not c.synthetic)
    return {
        "generated_at": _iso(now), "window_days": window_days,
        "cases_in_window": len(cs), "live_cases": live, "synthetic_cases": len(cs) - live,
        "exception_frequency_by_location": freq,
        "detection_to_review": _stats(d2r),
        "cycle_time": _stats(cycle),
        "throughput_per_week": dict(sorted(weeks.items())),
        "unresolved": len(unresolved),
        "overdue": sorted(overdue, key=lambda o: -o["age_h"]),
        "burndown": burndown,
    }


# --- Synthetic backfill from labelled telemetry -------------------------------------------------
_PRIORITY = {"COOLING_FAILURE": "High", "TEMP_EXCURSION": "High", "SENSOR_DROPOUT": "Medium"}


def label_episodes(rows_by_loc: dict[str, list[dict]]) -> list[dict]:
    """Contiguous non-NONE label runs per location -> one episode each (start ts, kind)."""
    eps = []
    for loc, rows in rows_by_loc.items():
        prev = "NONE"
        for r in rows:
            lab = r.get("label", "NONE") or "NONE"
            if lab != "NONE" and lab != prev:
                eps.append({"location_id": loc, "kind": lab, "detected_at": r["ts"]})
            prev = lab
    return sorted(eps, key=lambda e: e["detected_at"])


def backfill_from_labels(store: CaseStore, rows_by_loc: dict[str, list[dict]], days: int = 60,
                         seed: int = 7, now: datetime | None = None) -> int:
    """Create synthetic historical cases for labelled episodes in the last `days` of the data.

    Time is shifted so the last reading lands at `now`; review and close delays are seeded
    log-normal draws (median ~1.5 h to first action, ~20 h to close). A small share is left open.
    """
    eps = label_episodes(rows_by_loc)
    if not eps:
        return 0
    rng = random.Random(seed)
    last = max(_parse(e["detected_at"]) for e in eps)
    now = _parse(now) or _now()
    shift = now - last
    cutoff = last - timedelta(days=days)
    n = 0
    for i, e in enumerate(eps):
        det = _parse(e["detected_at"])
        if det < cutoff:
            continue
        det += shift
        created = det + timedelta(minutes=rng.choice((0, 30, 30, 60)))
        cid = f"SYN-{det:%y%m%d}-{e['location_id'][:3]}-{i:04d}"
        store.create(cid, e["location_id"], e["kind"], _PRIORITY.get(e["kind"], "Medium"),
                     detected_at=det, created_at=created, synthetic=True)
        start = created + timedelta(hours=rng.lognormvariate(0.4, 0.8))
        review = start + timedelta(hours=rng.lognormvariate(1.2, 0.7))
        close = review + timedelta(hours=rng.lognormvariate(2.3, 0.6))
        actor = rng.choice(("Naledi Mokoena", "Sipho Peters", "Aisha Dlamini", "Thandi Kumalo"))
        if start < now:
            store.transition(cid, "In progress", actor, "picked up", ts=start, assignee=actor)
        if review < now and rng.random() > 0.05:
            store.transition(cid, "Under review", "QA reviewer", "evidence checked", ts=review)
            if close < now and rng.random() > 0.05:
                store.transition(cid, "Closed", "QA reviewer", "disposition recorded", ts=close)
        n += 1
    return n
