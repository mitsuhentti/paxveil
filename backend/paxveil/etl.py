"""Operational ETL commands; the durable Watch scheduler runs these in scan jobs."""
import argparse
import json

from sqlalchemy import select, text

from paxveil.api import enqueue_scan
from paxveil.db import Project, SessionLocal, Subscription, now


def main():
    parser = argparse.ArgumentParser(prog="PAXVEIL ETL")
    parser.add_argument("command", choices=["refresh", "quality", "metrics"])
    args = parser.parse_args()
    with SessionLocal.begin() as db:
        if args.command == "refresh":
            count = 0
            for project in db.scalars(select(Project).join(Subscription).where(Subscription.enabled.is_(True))):
                enqueue_scan(db, project)
                count += 1
            print(json.dumps({"enqueued_projects": count, "at": now().isoformat()}))
        elif args.command == "quality":
            checks = {
                "orphan_scans": "SELECT COUNT(*) FROM scans s LEFT JOIN projects p ON s.project_id=p.id WHERE p.id IS NULL",
                "duplicate_findings": "SELECT COUNT(*) FROM (SELECT scan_id,advisory_id,package,version FROM findings GROUP BY scan_id,advisory_id,package,version HAVING COUNT(*)>1) q",
                "invalid_priority": "SELECT COUNT(*) FROM findings WHERE priority<0 OR priority>100",
                "completed_without_report": "SELECT COUNT(*) FROM scans WHERE status IN ('completed','partial') AND (report IS NULL OR CAST(report AS TEXT)='null')",
            }
            result = {name: db.scalar(text(query)) for name, query in checks.items()}
            print(json.dumps(result))
            if any(result.values()):
                raise SystemExit(1)
        else:
            rows = db.execute(text("SELECT * FROM scan_risk_metrics ORDER BY created_at DESC LIMIT 50")).mappings().all()
            print(json.dumps([dict(row) for row in rows], default=str))


if __name__ == "__main__":
    main()
