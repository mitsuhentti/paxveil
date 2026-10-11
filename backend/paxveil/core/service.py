from __future__ import annotations

import asyncio
import time
from collections import deque

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from .advisories import (
    CVE,
    affected_version,
    deduplicate,
    fixed_versions,
    package_affected,
    prioritize,
    references,
    score,
)
from .parsers import Dependency, InputError, environment, marker_status, parse
from .sources import SourceError, Sources


def summarize_sources(records: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record["name"], []).append(record)
    result = []
    for name, rows in groups.items():
        errors = [
            x.get("error", "Source lookup unavailable")
            for x in rows
            if x["status"] not in {"ok", "cached"}
        ]
        dates = [x["fetched_at"] for x in rows if x.get("fetched_at")]
        result.append(
            {
                "name": name,
                "status": "partial"
                if errors and dates
                else "unavailable"
                if errors
                else "cached"
                if all(x["status"] == "cached" for x in rows)
                else "ok",
                "fetched_at": max(dates) if dates else None,
                "requests": len(rows),
                "snapshots": list(
                    dict.fromkeys(
                        x["snapshot_hash"] for x in rows if x.get("snapshot_hash")
                    )
                ),
                **({"error": "; ".join(dict.fromkeys(errors))} if errors else {}),
            }
        )
    return result


async def scan(
    filename: str,
    content: bytes,
    python_version: str = "3.11",
    platform: str = "linux",
    refresh: bool = False,
) -> dict:
    started = time.monotonic()
    parsed = parse(filename, content, python_version, platform)
    env = environment(python_version, platform)
    warnings = list(parsed.warnings)
    warnings.append(
        "This is a known-vulnerability version analysis. Application reachability and exploitability are not tested."
    )
    active = [
        dep
        for dep in parsed.dependencies
        if dep.version and dep.status in {"active", "uncertain"}
    ]
    findings: list[dict] = []
    metadata: dict[str, dict] = {}
    edges = list(parsed.edges)
    osv_complete = True
    async with Sources(refresh=refresh) as sources:

        async def metadata_for(dep: Dependency):
            try:
                value = await sources.release(dep.name, dep.version)
                metadata[dep.id] = value
                requirement = value.get("info", {}).get("requires_python")
                if requirement:
                    from packaging.specifiers import SpecifierSet

                    try:
                        if Version(env["python_full_version"]) not in SpecifierSet(
                            requirement
                        ):
                            warnings.append(
                                f"{dep.name}=={dep.version} declares Requires-Python {requirement}; the submitted environment may be incompatible."
                            )
                    except ValueError:
                        warnings.append(
                            f"{dep.name}: invalid Requires-Python metadata from PyPI."
                        )
            except SourceError as exc:
                if exc.status_code == 404:
                    dep.status = "version_not_found"
                    warnings.append(
                        f"{dep.name}=={dep.version}: this release was not found on PyPI; vulnerability lookup was skipped."
                    )
                else:
                    warnings.append(
                        f"{dep.name}=={dep.version}: PyPI metadata unavailable; exact uploaded pin remains unverified."
                    )

        await asyncio.gather(*(metadata_for(dep) for dep in active))
        eligible = [dep for dep in active if dep.status != "version_not_found"]
        version_queries = list(
            {
                (x.name, x.version): {"name": x.name, "version": x.version}
                for x in eligible
            }.values()
        )
        matches = {}
        for offset in range(0, len(version_queries), 100):
            try:
                matches.update(
                    await sources.osv_batch(version_queries[offset : offset + 100])
                )
            except SourceError as exc:
                osv_complete = False
                warnings.append(
                    f"{exc}. Vulnerability lookup is incomplete; an empty findings list is not a clean result."
                )
        advisory_ids = list(
            dict.fromkeys(
                identity for values in matches.values() for identity in values
            )
        )
        advisories: dict[str, dict] = {}

        async def load_advisory(identity: str):
            nonlocal osv_complete
            try:
                value = await sources.advisory(identity)
                if not value.get("withdrawn"):
                    advisories[identity] = value
            except SourceError as exc:
                osv_complete = False
                warnings.append(f"{exc}: advisory details could not be retrieved.")

        await asyncio.gather(*(load_advisory(identity) for identity in advisory_ids))
        cves = sorted(
            {
                alias
                for advisory in advisories.values()
                for alias in [advisory.get("id", ""), *advisory.get("aliases", [])]
                if CVE.fullmatch(alias)
            }
        )
        epss: dict = {}
        kev: set[str] | None = None
        if cves:

            async def enrich_epss():
                nonlocal epss
                try:
                    epss = await sources.epss(cves)
                except SourceError as exc:
                    warnings.append(f"{exc}: EPSS probabilities remain unknown.")

            async def enrich_kev():
                nonlocal kev
                try:
                    kev = await sources.kev()
                except SourceError as exc:
                    warnings.append(
                        f"{exc}: known exploitation status remains unknown."
                    )

            await asyncio.gather(enrich_epss(), enrich_kev())
        for dep in eligible:
            for identity in matches.get((dep.name, dep.version), []):
                advisory = advisories.get(identity)
                if not advisory:
                    continue
                aliases = advisory.get("aliases", [])
                candidates = [epss[c] for c in [identity, *aliases] if c in epss]
                best = (
                    max(candidates, key=lambda item: float(item["epss"]))
                    if candidates
                    else None
                )
                probability = float(best["epss"]) if best else None
                cvss, severity = score(advisory)
                exploited = (
                    any(c in kev for c in [identity, *aliases])
                    if kev is not None
                    else None
                )
                priority, reasons = prioritize(
                    cvss, severity, probability, exploited, dep.direct
                )
                findings.append(
                    {
                        "id": identity,
                        "aliases": aliases,
                        "advisory_ids": [identity],
                        "package": dep.name,
                        "version": dep.version,
                        "summary": advisory.get("summary")
                        or (
                            advisory.get("details", "")[:500]
                            or "No advisory summary supplied."
                        ),
                        "severity": severity,
                        "cvss": cvss,
                        "epss": probability,
                        "epss_date": best.get("date") if best else None,
                        "kev": exploited,
                        "priority": priority,
                        "priority_reasons": reasons,
                        "affected": package_affected(advisory, dep.name),
                        "fixed_versions": fixed_versions(advisory, dep.name),
                        "references": references(advisory),
                        "published": advisory.get("published"),
                        "modified": advisory.get("modified"),
                        "status": "version_match",
                        "confidence": {
                            "basis": "OSV package/version query",
                            "pin": "exact",
                            "release_verified": dep.id in metadata,
                            "environment": dep.status,
                            "application_reachability": "not_tested",
                        },
                    }
                )
        by_name: dict[str, list[Dependency]] = {}
        for dep in active:
            by_name.setdefault(dep.name, []).append(dep)
        for dep in active:
            value = metadata.get(dep.id, {})
            for raw in value.get("info", {}).get("requires_dist") or []:
                try:
                    req = Requirement(raw)
                except InvalidRequirement:
                    warnings.append(
                        f"{dep.name}: invalid Requires-Dist metadata was ignored."
                    )
                    continue
                if req.url:
                    warnings.append(
                        f"{dep.name}: direct-URL metadata dependency was not followed."
                    )
                    continue
                if (
                    marker_status(
                        str(req.marker) if req.marker else None, env, dep.extras
                    )
                    == "excluded"
                ):
                    continue
                targets = [
                    target
                    for target in by_name.get(canonicalize_name(req.name), [])
                    if target.version
                    and Version(target.version) in req.specifier
                    and target.status != "excluded"
                ]
                if len(targets) == 1:
                    edges.append(
                        {
                            "source": dep.id,
                            "target": targets[0].id,
                            "source_type": "PyPI release metadata",
                        }
                    )
                elif not targets:
                    warnings.append(
                        f"{dep.name} → {canonicalize_name(req.name)}: required version not uniquely present in the submitted file; transitive coverage may be incomplete."
                    )

        # deps.dev validates independent upstream requirement metadata; its generic
        # Linux resolution is never substituted for the user's environment.
        async def crosscheck(dep: Dependency):
            try:
                await sources.deps_requirements(dep.name, dep.version)
            except SourceError as exc:
                warnings.append(
                    f"{dep.name}: {exc}; independent metadata cross-check unavailable."
                )

        await asyncio.gather(*(crosscheck(dep) for dep in eligible[:10]))
        if len(eligible) > 10:
            warnings.append(
                "deps.dev metadata cross-check was bounded to the first 10 recorded releases; OSV covers all eligible exact pins."
            )
        source_records = summarize_sources(sources.records)
    findings = deduplicate(findings)
    nodes = list(
        {
            dep.id: {
                "id": dep.id,
                "name": dep.name,
                "version": dep.version,
                "direct": dep.direct,
                "status": dep.status,
            }
            for dep in parsed.dependencies
        }.values()
    )
    known_nodes = {node["id"] for node in nodes}
    edges = list(
        {
            (edge["source"], edge["target"]): edge
            for edge in edges
            if edge["source"] in known_nodes and edge["target"] in known_nodes
        }.values()
    )
    unresolved = any(
        dep.status not in {"active", "excluded"} for dep in parsed.dependencies
    )
    metadata_partial = any(
        source["status"] in {"unavailable", "partial"} for source in source_records
    )
    completeness = (
        "partial"
        if not osv_complete or unresolved or metadata_partial
        else "recorded_versions_checked"
    )
    return {
        "dependencies": [dep.json() for dep in parsed.dependencies],
        "findings": findings,
        "graph": {"nodes": nodes, "edges": edges},
        "warnings": list(dict.fromkeys(warnings)),
        "sources": source_records,
        "stats": {
            "dependencies": len(parsed.dependencies),
            "findings": len(findings),
            "duration_seconds": round(time.monotonic() - started, 3),
        },
        "completeness": completeness,
        "vulnerability_lookup_complete": osv_complete and not unresolved,
        "environment": {"python_version": python_version, "platform": platform},
        "input_format": parsed.format,
        "checked_at": max(
            [row["fetched_at"] for row in source_records if row.get("fetched_at")]
            or [None]
        ),
    }


def dependency_path(report: dict, package: str, version: str | None) -> list[str]:
    target = f"{package}=={version or '?'}"
    graph = report.get("graph", {})
    roots = [n["id"] for n in graph.get("nodes", []) if n.get("direct") is True]
    adjacency: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        adjacency.setdefault(edge["source"], []).append(edge["target"])
    queue = deque([[root] for root in roots])
    visited = set()
    while queue:
        path = queue.popleft()
        if path[-1] == target:
            return path
        if path[-1] in visited:
            continue
        visited.add(path[-1])
        queue.extend(
            [*path, child]
            for child in adjacency.get(path[-1], [])
            if child not in visited
        )
    return [target]


async def fire(cve: str, reports: list[dict]) -> dict:
    cve = cve.strip().upper()
    if not CVE.fullmatch(cve):
        raise InputError("Enter a CVE identifier, e.g. CVE-2024-35195.")
    advisories: dict[str, dict] = {}
    limitations = [
        "A version match does not demonstrate application reachability or exploitability.",
        "A single lock file may omit root paths, extras or platform selection.",
    ]
    source_failed = False
    async with Sources(refresh=True) as sources:
        known_ids = {
            finding["id"]
            for report in reports
            for finding in report.get("findings", [])
            if cve in [finding.get("id"), *finding.get("aliases", [])]
        }
        for identity in {cve, *known_ids}:
            try:
                advisory = await sources.advisory(identity)
                if not advisory.get("withdrawn") and cve in [
                    advisory.get("id"),
                    *advisory.get("aliases", []),
                ]:
                    advisories[identity] = advisory
            except SourceError as exc:
                if exc.status_code != 404:
                    source_failed = True
                    limitations.append(str(exc))
        matches = []
        for report in reports:
            for dep in report.get("dependencies", []):
                if dep.get("status") == "excluded":
                    continue
                for advisory in advisories.values():
                    status = affected_version(advisory, dep["name"], dep.get("version"))
                    if status == "no_match":
                        continue
                    if dep.get("status") in {
                        "unsupported",
                        "uncertain",
                        "version_not_found",
                    }:
                        status = "possible"
                    matches.append(
                        {
                            "project_id": report.get("project_id"),
                            "project_name": report.get("project_name"),
                            "package": dep["name"],
                            "version": dep.get("version"),
                            "status": status,
                            "advisory_id": advisory["id"],
                            "path": dependency_path(
                                report, dep["name"], dep.get("version")
                            ),
                            "fixed_versions": fixed_versions(advisory, dep["name"]),
                            "references": references(advisory),
                        }
                    )
                if not advisories and any(
                    cve in [f.get("id"), *f.get("aliases", [])]
                    and f.get("package") == dep["name"]
                    for f in report.get("findings", [])
                ):
                    matches.append(
                        {
                            "project_id": report.get("project_id"),
                            "project_name": report.get("project_name"),
                            "package": dep["name"],
                            "version": dep.get("version"),
                            "status": "insufficient_data",
                            "advisory_id": cve,
                            "path": dependency_path(
                                report, dep["name"], dep.get("version")
                            ),
                            "fixed_versions": [],
                            "references": [],
                        }
                    )
        if not advisories:
            limitations.append(
                "OSV has no retrievable advisory for this CVE or its aliases in your existing reports. Absence is insufficient to establish that projects are unaffected."
            )
        result_status = (
            "insufficient_data"
            if not advisories or source_failed
            else "confirmed"
            if any(row["status"] == "confirmed" for row in matches)
            else "possible"
            if matches
            else "no_match"
        )
        summary = [
            {
                "id": row["id"],
                "aliases": row.get("aliases", []),
                "summary": row.get("summary"),
                "references": references(row),
                "affected": row.get("affected", []),
            }
            for row in advisories.values()
        ]
        deduped_matches = list(
            {
                (row["project_id"], row["package"], row["version"], row["status"]): row
                for row in matches
            }.values()
        )
        return {
            "cve": cve,
            "status": result_status,
            "advisories": summary,
            "matches": deduped_matches,
            "limitations": limitations,
            "sources": summarize_sources(sources.records),
        }


async def fixlab(report: dict) -> dict:
    from .fixlab import simulate

    return await simulate(report)
