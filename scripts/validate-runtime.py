"""Read-only local startup, persistence and HTTP latency evidence.

Run with the repository's Python environment. Never exports database credentials
or report contents. --project names an existing disposable QA project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
from paxveil.db import FindingState, Project, Scan, SessionLocal, Subscription  # noqa: E402


def saved_state(project_id: str) -> dict:
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project is None:
            raise SystemExit("QA project not found")
        scans = db.scalars(select(Scan).where(Scan.project_id == project_id).order_by(Scan.id)).all()
        states = db.scalars(select(FindingState).where(FindingState.project_id == project_id).order_by(FindingState.id)).all()
        subscription = db.get(Subscription, project_id)

        def row(value):
            return {column.name: getattr(value, column.name) for column in value.__table__.columns}

        material = {"project": row(project), "scans": [row(s) for s in scans],
                    "finding_states": [row(s) for s in states],
                    "subscription": row(subscription) if subscription else None}
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()
        return {"sha256": digest, "saved_scans": len(scans), "finding_states": len(states)}


def latency(client: httpx.Client, url: str) -> dict:
    samples = []
    for _ in range(20):
        started = time.perf_counter()
        response = client.get(url)
        response.raise_for_status()
        samples.append((time.perf_counter() - started) * 1000)
    return {"samples": len(samples), "median_ms": round(statistics.median(samples), 2),
            "p95_ms": round(sorted(samples)[18], 2), "max_ms": round(max(samples), 2)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["snapshot", "check"])
    parser.add_argument("--project", required=True, type=lambda text: str(UUID(text)))
    args = parser.parse_args()
    baseline_path = REPO / "runtime" / "persistence-baseline.json"
    baseline_path.parent.mkdir(exist_ok=True)
    current = saved_state(args.project)
    if args.mode == "snapshot":
        baseline_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        print("QA persistence baseline saved; no database data modified.")
        return
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    with httpx.Client(trust_env=False, timeout=10) as client:
        evidence = {"captured_at": datetime.now(UTC).isoformat(),
                    "scope": "Local sequential HTTP samples; not a load test or production SLA",
                    "persistence_unchanged": current == baseline,
                    "qa_saved_state": current,
                    "api_health": latency(client, "http://127.0.0.1:8000/api/health"),
                    "web_html": latency(client, "http://127.0.0.1:3000/")}
    (REPO / "docs" / "RUNTIME_VALIDATION.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["persistence_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
