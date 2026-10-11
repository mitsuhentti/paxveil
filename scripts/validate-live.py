"""Opt-in gentle live acceptance check. Creates a new isolated local validation account."""
import json
import secrets
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
REPO = Path(__file__).resolve().parents[1]


def wait_scan(client, identifier):
    for _ in range(180):
        response = client.get(f"/api/scans/{identifier}")
        response.raise_for_status()
        row = response.json()
        if row["status"] in ["completed", "partial", "failed"]:
            assert row["status"] != "failed", row
            return row
        time.sleep(2)
    raise RuntimeError("Scan did not complete within 6 minutes")


def main():
    start = time.perf_counter()
    username = "validation_" + secrets.token_hex(4)
    password = secrets.token_urlsafe(20)
    runtime = REPO / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "test-account.json").write_text(json.dumps({"username": username, "password": password}), encoding="utf-8")
    results = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "api": BASE, "username": username, "checks": {}}
    with httpx.Client(base_url=BASE, timeout=60, trust_env=False) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        results["checks"]["health"] = health.json()
        response = client.post("/api/auth/register", json={"username": username, "password": password})
        response.raise_for_status()
        results["checks"]["registration"] = response.status_code
        for filename, content in [("../requirements.txt", b"requests==2.31.0"), ("uv.lock", b"this is not toml !")]:
            response = client.post("/api/projects", data={"name": "Rejected input"}, files={"file": (filename, content)})
            assert response.status_code in [413, 422], response.text
            results["checks"]["reject_"+filename.replace("/", "_")] = response.status_code
        response = client.post("/api/projects", data={"name": "Requests live validation"}, files={"file": ("requirements.txt", b"requests==2.31.0\n")})
        response.raise_for_status()
        project = response.json()
        (runtime / "test-account.json").write_text(json.dumps({"username": username, "password": password, "project_id": project["id"], "scan_id": project["latest_scan"]["id"]}), encoding="utf-8")
        scan = wait_scan(client, project["latest_scan"]["id"])
        report = scan["report"]
        results["project_id"] = project["id"]
        results["scan_id"] = scan["id"]
        results["checks"]["vulnerable_scan"] = {"status": scan["status"], "stats": report["stats"], "completeness": report["completeness"], "advisories": [f["id"] for f in report["findings"]], "sources": report["sources"], "warnings": report["warnings"]}
        assert report["findings"], "Expected known requests advisories from real OSV"
        assert any("CVE-2024-35195" in f.get("aliases", []) for f in report["findings"])
        response = client.post("/api/fire", json={"cve": "CVE-2024-35195"})
        response.raise_for_status()
        results["checks"]["fire"] = response.json()
        assert any(m["project_id"] == project["id"] and m["status"] == "confirmed" for m in response.json()["matches"])
        response = client.put(f"/api/projects/{project['id']}/watch", json={"enabled": True})
        response.raise_for_status()
        assert client.get(f"/api/projects/{project['id']}").json()["watch"] is True
        results["checks"]["watch_persisted"] = True
        response = client.post("/api/projects", data={"name": "Sampleproject live validation"}, files={"file": ("requirements.txt", b"sampleproject==4.0.0\n")})
        response.raise_for_status()
        clean = wait_scan(client, response.json()["latest_scan"]["id"])
        results["checks"]["sampleproject_scan"] = {"stats": clean["report"]["stats"], "completeness": clean["report"]["completeness"], "sources": clean["report"]["sources"]}
        # Other-account requests must never reveal this project's reports or jobs.
        with httpx.Client(base_url=BASE, timeout=30) as other:
            other.post("/api/auth/register", json={"username": username+"_other", "password": password}).raise_for_status()
            denied = other.get(f"/api/projects/{project['id']}")
            assert denied.status_code == 404
            results["checks"]["cross_user_project"] = denied.status_code
        response = client.post(f"/api/scans/{scan['id']}/fixlab")
        response.raise_for_status()
        identifier = response.json()["id"]
        for _ in range(330):
            job = client.get(f"/api/jobs/{identifier}").json()
            if job["status"] in ["succeeded", "failed"]:
                assert job["status"] == "succeeded", job
                results["checks"]["fixlab"] = job["result"]
                break
            time.sleep(2)
        else:
            raise RuntimeError("FixLab did not complete within 11 minutes")
        (runtime / "test-account.json").write_text(json.dumps({"username": username, "password": password, "project_id": project["id"], "scan_id": scan["id"]}), encoding="utf-8")
    results["duration_seconds"] = round(time.perf_counter()-start, 3)
    (REPO / "docs" / "LIVE_ACCEPTANCE.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"checks": list(results["checks"]), "duration_seconds": results["duration_seconds"], "project_id": project["id"]}))


if __name__ == "__main__":
    main()
