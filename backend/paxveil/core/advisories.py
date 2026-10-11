from __future__ import annotations

import re

from cvss import CVSS2, CVSS3, CVSS4
from cvss.exceptions import CVSSError
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

CVE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,19}$")


def score(advisory: dict) -> tuple[float | None, str]:
    numbers: list[float] = []
    for item in advisory.get("severity", []):
        vector = str(item.get("score", ""))
        try:
            model = (
                CVSS4
                if vector.startswith("CVSS:4")
                else CVSS3
                if vector.startswith("CVSS:3")
                else CVSS2
            )
            numbers.append(float(model(vector).scores()[0]))
        except (CVSSError, ValueError, KeyError, TypeError):
            continue
    number = max(numbers) if numbers else None
    if number is not None:
        return (
            number,
            "critical"
            if number >= 9
            else "high"
            if number >= 7
            else "medium"
            if number >= 4
            else "low",
        )
    raw = str(advisory.get("database_specific", {}).get("severity", "")).lower()
    if raw in {"critical", "high", "medium", "moderate", "low"}:
        return None, "medium" if raw == "moderate" else raw
    return None, "unknown"


def package_affected(advisory: dict, package: str) -> list[dict]:
    return [
        row
        for row in advisory.get("affected", [])
        if row.get("package", {}).get("ecosystem") == "PyPI"
        and canonicalize_name(row.get("package", {}).get("name", "")) == package
    ]


def fixed_versions(advisory: dict, package: str) -> list[str]:
    values = {
        event["fixed"]
        for row in package_affected(advisory, package)
        for interval in row.get("ranges", [])
        for event in interval.get("events", [])
        if "fixed" in event and interval.get("type") != "GIT"
    }
    valid: list[tuple[Version, str]] = []
    for value in values:
        try:
            valid.append((Version(value), value))
        except InvalidVersion:
            continue
    return [raw for _, raw in sorted(valid)]


def references(advisory: dict) -> list[str]:
    return list(
        dict.fromkeys(
            r["url"]
            for r in advisory.get("references", [])
            if isinstance(r, dict)
            and str(r.get("url", "")).startswith(("https://", "http://"))
        )
    )


def affected_version(advisory: dict, package: str, version: str | None) -> str:
    rows = package_affected(advisory, package)
    if not rows:
        return "no_match"
    if not version:
        return "possible"
    try:
        current = Version(version)
    except InvalidVersion:
        return "insufficient_data"
    understood = False
    for row in rows:
        if version in row.get("versions", []):
            return "confirmed"
        # Explicit versions are exhaustive only if there are no ranges.
        if row.get("versions") and not row.get("ranges"):
            understood = True
        for interval in row.get("ranges", []):
            if interval.get("type") not in {"ECOSYSTEM", "SEMVER"}:
                continue
            active = False
            try:
                for event in interval.get("events", []):
                    if "introduced" in event:
                        active = event["introduced"] == "0" or current >= Version(
                            event["introduced"]
                        )
                        understood = True
                    if "fixed" in event:
                        if active and current < Version(event["fixed"]):
                            return "confirmed"
                        active = False
                    if "last_affected" in event:
                        if active and current <= Version(event["last_affected"]):
                            return "confirmed"
                        active = False
                    if "limit" in event:
                        if active and current < Version(event["limit"]):
                            return "confirmed"
                        active = False
                if active:
                    return "confirmed"
            except InvalidVersion:
                continue
    return "no_match" if understood else "insufficient_data"


def prioritize(
    cvss: float | None,
    severity: str,
    epss: float | None,
    kev: bool | None,
    direct: bool | None,
) -> tuple[int, list[str]]:
    # A policy score, deliberately separate from any exploitation probability.
    base = (
        round(cvss * 5)
        if cvss is not None
        else {"critical": 45, "high": 35, "medium": 20, "low": 8, "unknown": 10}[
            severity
        ]
    )
    reasons = [
        f"Impact component: {base}/50 from "
        + (
            f"CVSS {cvss:.1f}."
            if cvss is not None
            else f"{severity} source severity; CVSS unavailable."
        )
    ]
    if epss is not None:
        addition = round(20 * epss)
        base += addition
        reasons.append(
            f"FIRST EPSS {epss:.2%} contributes {addition}/20; EPSS predicts CVE exploitation in the wild."
        )
    else:
        reasons.append("EPSS unavailable; no exploitation probability was inferred.")
    if kev:
        base += 25
        reasons.append(
            "CISA KEV listing adds 25: exploitation in the wild is documented."
        )
    elif kev is None:
        reasons.append("CISA KEV source unavailable; exploitation evidence is unknown.")
    if direct:
        base += 5
        reasons.append("Submitted root dependency adds 5 for remediation visibility.")
    reasons.append(
        "Priority is a PAXVEIL triage policy (0–100), not proof of application reachability or exploitability."
    )
    return min(100, base), reasons


def deduplicate(findings: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for finding in findings:
        identities = {finding["id"], *finding["aliases"]}
        matching = [
            row
            for row in groups
            if row["package"] == finding["package"]
            and row["version"] == finding["version"]
            and identities.intersection([row["id"], *row["aliases"]])
        ]
        if not matching:
            groups.append(finding)
            continue
        merged = [finding, *matching]
        # Prefer richer severity evidence, then GHSA records for readable remediation.
        best = max(
            merged,
            key=lambda row: (
                row["cvss"] is not None,
                row["cvss"] or 0,
                row["id"].startswith("GHSA-"),
            ),
        )
        result = dict(best)
        result["aliases"] = sorted(
            {identity for row in merged for identity in [row["id"], *row["aliases"]]}
            - {result["id"]}
        )
        result["references"] = list(
            dict.fromkeys(url for row in merged for url in row["references"])
        )
        result["fixed_versions"] = list(
            dict.fromkeys(v for row in merged for v in row["fixed_versions"])
        )
        result["advisory_ids"] = sorted(
            {
                identity
                for row in merged
                for identity in row.get("advisory_ids", [row["id"]])
            }
        )
        for row in matching:
            groups.remove(row)
        groups.append(result)
    return sorted(groups, key=lambda row: (-row["priority"], row["package"], row["id"]))
