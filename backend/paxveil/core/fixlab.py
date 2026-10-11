from __future__ import annotations

import asyncio

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .resolver import ResolutionError, resolve
from .sources import SourceError, Sources

STRATEGIES = [
    (
        "Minimal Change",
        "Smallest newer stable release in the same major/minor family, subject to recorded non-pin bounds.",
    ),
    (
        "Balanced",
        "Newest stable release in the same major family, subject to recorded non-pin bounds.",
    ),
    (
        "Maximum Coverage",
        "Newest stable release across major families; original non-pin bounds are relaxed explicitly.",
    ),
]


def stats(report: dict) -> dict:
    return {
        "dependencies": len(report.get("dependencies", [])),
        "findings": len(report.get("findings", [])),
        "known_vulnerabilities": len(report.get("findings", [])),
        "completeness": report.get("completeness", "unknown"),
    }


def candidates(
    metadata: dict, current: str, python_version: str, specifier: str, strategy: str
) -> list[str]:
    current_version = Version(current)
    # Exact pins describe the current state; other bounds are preserved for A/B.
    try:
        bounds = SpecifierSet(
            ",".join(
                str(s)
                for s in SpecifierSet(specifier)
                if s.operator not in {"==", "==="}
            )
        )
    except InvalidSpecifier:
        bounds = SpecifierSet()
    choices = []
    for raw, files in metadata.get("releases", {}).items():
        try:
            candidate = Version(raw)
        except InvalidVersion:
            continue
        if (
            candidate <= current_version
            or candidate.is_prerelease
            or candidate.is_devrelease
            or candidate.local
        ):
            continue
        if strategy != "Maximum Coverage" and candidate not in bounds:
            continue
        if (
            strategy == "Minimal Change"
            and candidate.release[:2] != current_version.release[:2]
        ):
            continue
        if (
            strategy == "Balanced"
            and candidate.release[0] != current_version.release[0]
        ):
            continue
        allowed = []
        for file in files:
            if file.get("yanked") or file.get("packagetype") != "bdist_wheel":
                continue
            required = file.get("requires_python")
            try:
                if required and Version(python_version) not in SpecifierSet(required):
                    continue
            except InvalidSpecifier:
                continue
            allowed.append(file)
        if allowed:
            choices.append((candidate, raw))
    choices.sort(reverse=strategy != "Minimal Change")
    return [raw for _, raw in choices]


async def simulate(report: dict) -> dict:
    from .service import scan, summarize_sources

    limitations = [
        "Resolution uses official PyPI binary metadata; package code and application tests are never executed.",
        "A resolved environment is a proposal, not a guarantee of behavioral compatibility.",
        "Target architecture is x86_64; machine, optional extras and original root bounds may be incomplete.",
        "requirements.txt pins are treated as simulation roots. poetry.lock without a project manifest has unknown roots and cannot be resolved faithfully.",
        "Maximum Coverage may relax non-pin version bounds; review and test the proposal before applying.",
    ]
    env = report.get("environment", {})
    python_version = env.get("python_version", "3.11")
    platform = env.get("platform", "linux")
    active = [
        dep
        for dep in report.get("dependencies", [])
        if dep.get("status", "active") not in {"excluded"}
    ]
    unknown = [
        dep
        for dep in active
        if not dep.get("version")
        or dep.get("status")
        in {"unsupported", "version_not_found", "uncertain", "unresolved"}
    ]
    roots = [dep for dep in active if dep.get("direct") is True]
    vulnerable = {finding["package"] for finding in report.get("findings", [])}
    before = stats(report)
    results = []
    async with Sources() as sources:
        metadata: dict[str, dict] = {}
        errors = []

        async def project(dep):
            try:
                metadata[dep["name"]] = await sources.project(dep["name"])
            except SourceError as exc:
                errors.append(str(exc))

        await asyncio.gather(
            *(
                project(dep)
                for dep in active
                if dep["name"] in vulnerable and dep.get("version")
            )
        )
        for name, reason in STRATEGIES:
            row = {
                "name": name,
                "updates": [],
                "before": before,
                "after": None,
                "conflicts": [],
                "uncertainties": list(errors),
                "graph_changes": {"added": [], "removed": [], "changed": []},
                "reason": reason,
                "status": "insufficient_data",
            }
            if unknown or not roots:
                row["uncertainties"].append(
                    "Exact, supported dependencies and known project roots are required for a faithful resolution. Upload a complete pinned requirements file or uv.lock with a project root."
                )
                results.append(row)
                continue
            if not vulnerable:
                row["uncertainties"].append(
                    "The source report contains no known findings. No remediation target was inferred."
                )
                results.append(row)
                continue
            targets: dict[str, str] = {}
            for dep in active:
                if dep["name"] not in vulnerable or dep["name"] not in metadata:
                    continue
                options = candidates(
                    metadata[dep["name"]],
                    dep["version"],
                    python_version,
                    dep.get("specifier", ""),
                    name,
                )
                if not options:
                    row["uncertainties"].append(
                        f"{dep['name']}: no eligible newer stable wheel release for this strategy and Python version."
                    )
                    continue
                # Smallest advisory fixed boundary provides evidence for A when
                # present. The resolved result is then actually rescanned.
                if name == "Minimal Change":
                    boundaries = [
                        Version(v)
                        for finding in report.get("findings", [])
                        if finding["package"] == dep["name"]
                        for v in finding.get("fixed_versions", [])
                        if Version(v) > Version(dep["version"])
                        and Version(v).release[:2]
                        == Version(dep["version"]).release[:2]
                    ]
                    if boundaries:
                        options = [
                            value
                            for value in options
                            if Version(value) >= max(boundaries)
                        ]
                if options:
                    targets[dep["name"]] = options[0]
                    row["updates"].append(
                        {
                            "package": dep["name"],
                            "from": dep["version"],
                            "to": options[0],
                            "release_verified": True,
                        }
                    )
            if not targets:
                row["uncertainties"].append(
                    "No verified update proposal could be formed within this strategy."
                )
                results.append(row)
                continue
            requirements = []
            for dep in roots:
                extras = (
                    "[" + ",".join(dep.get("extras", [])) + "]"
                    if dep.get("extras")
                    else ""
                )
                pin = targets.get(dep["name"], dep["version"])
                requirements.append(f"{dep['name']}{extras}=={pin}")
            # Updating a transitive package adds an explicit constraint while
            # retaining pinned roots, exposing actual compatibility conflicts.
            root_names = {dep["name"] for dep in roots}
            requirements.extend(
                f"{package}=={version}"
                for package, version in targets.items()
                if package not in root_names
            )
            try:
                resolution = await resolve(requirements, python_version, platform)
                after_report = await scan(
                    "requirements.txt", resolution["content"], python_version, platform
                )
                row["after"] = stats(after_report)
                row["status"] = (
                    "resolved"
                    if after_report["completeness"] == "recorded_versions_checked"
                    else "insufficient_data"
                )
                row["uncertainties"].extend(after_report["warnings"])
                row["after_findings"] = after_report["findings"]
                old = {dep["name"]: dep["version"] for dep in active}
                new = {
                    dep["name"]: dep["version"] for dep in after_report["dependencies"]
                }
                row["graph_changes"] = {
                    "added": [
                        {"package": package, "version": version}
                        for package, version in new.items()
                        if package not in old
                    ],
                    "removed": [
                        {"package": package, "version": version}
                        for package, version in old.items()
                        if package not in new
                    ],
                    "changed": [
                        {"package": package, "from": old[package], "to": version}
                        for package, version in new.items()
                        if package in old and old[package] != version
                    ],
                }
                row["updates"] = [
                    {**change, "release_verified": True}
                    for change in row["graph_changes"]["changed"]
                ]
                row["resolver"] = resolution["resolver"]
                row["after_graph"] = after_report["graph"]
                row["sources"] = after_report["sources"]
            except (ResolutionError, ValueError) as exc:
                row["status"] = "conflict"
                row["conflicts"].append(str(exc))
                row["uncertainties"].append(
                    "No valid binary-only resolution was produced. Vulnerabilities after this proposal were not evaluated."
                )
            results.append(row)
        return {
            "strategies": results,
            "limitations": limitations,
            "sources": summarize_sources(sources.records),
        }
