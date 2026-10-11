from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath

from packaging.markers import InvalidMarker, Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

MAX_BYTES = 1024 * 1024
MAX_DEPENDENCIES = 300
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class InputError(ValueError):
    """A dependency file cannot be safely interpreted."""


def environment(
    python_version: str = "3.11", platform: str = "linux"
) -> dict[str, str]:
    if not re.fullmatch(r"3\.(?:[8-9]|[1-9][0-9])(?:\.[0-9]{1,2})?", python_version):
        raise InputError("Python version must be 3.8 or later, e.g. 3.11.")
    if platform not in {"linux", "windows", "darwin"}:
        raise InputError("Platform must be linux, windows or darwin.")
    parts = python_version.split(".")
    return {
        "python_version": ".".join(parts[:2]),
        "python_full_version": python_version
        if len(parts) == 3
        else f"{python_version}.0",
        "os_name": "nt" if platform == "windows" else "posix",
        "sys_platform": "win32" if platform == "windows" else platform,
        "platform_system": {"linux": "Linux", "windows": "Windows", "darwin": "Darwin"}[
            platform
        ],
        "platform_machine": "x86_64",
        "platform_release": "",
        "platform_version": "",
        "platform_python_implementation": "CPython",
        "implementation_name": "cpython",
        "implementation_version": python_version
        if len(parts) == 3
        else f"{python_version}.0",
        "extra": "",
    }


def marker_status(
    marker: str | None, env: dict[str, str], extras: list[str] | None = None
) -> str:
    if not marker:
        return "active"
    try:
        parsed = Marker(marker)
        # Machine/kernel values were not supplied by the user. Never infer them.
        if any(
            key in marker
            for key in ("platform_machine", "platform_release", "platform_version")
        ):
            return "uncertain"
        choices = extras or [""]
        return (
            "active"
            if any(parsed.evaluate({**env, "extra": x}) for x in choices)
            else "excluded"
        )
    except (InvalidMarker, KeyError, ValueError):
        return "uncertain"


@dataclass
class Dependency:
    name: str
    version: str | None
    direct: bool | None
    source: str
    marker: str | None = None
    status: str = "active"
    specifier: str = ""
    extras: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.name}=={self.version or '?'}"

    def json(self) -> dict:
        return asdict(self)


@dataclass
class Parsed:
    dependencies: list[Dependency]
    edges: list[dict]
    warnings: list[str]
    format: str


def _dependency(
    name: str,
    version: object,
    source: str,
    direct: bool | None,
    marker: str | None,
    env: dict,
) -> Dependency:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise InputError("Invalid package name in dependency file.")
    normalized = canonicalize_name(name)
    exact: str | None = str(version) if version is not None else None
    if exact:
        try:
            Version(exact)
        except InvalidVersion:
            exact = None
    status = marker_status(marker, env)
    if exact is None and status != "excluded":
        status = "unresolved"
    return Dependency(normalized, exact, direct, source, marker, status)


def _requirements(text: str, env: dict) -> Parsed:
    deps: list[Dependency] = []
    warnings = [
        "A requirements file does not establish whether all transitive dependencies are pinned. Submitted entries are treated as roots for simulation."
    ]
    joined = re.sub(r"\\\r?\n\s*", " ", text)
    for number, raw in enumerate(joined.splitlines(), 1):
        line = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            warnings.append(
                f"Line {number}: installer option, include, editable or index directive was ignored; no files or URLs were followed."
            )
            continue
        line = re.sub(r"\s+--hash=[A-Za-z0-9:]+", "", line)
        try:
            req = Requirement(line)
        except InvalidRequirement as exc:
            raise InputError(
                f"Invalid requirement on line {number}: {str(exc).splitlines()[0]}"
            ) from exc
        if req.url:
            deps.append(
                Dependency(
                    canonicalize_name(req.name),
                    None,
                    True,
                    "unsupported-url",
                    str(req.marker) if req.marker else None,
                    "unsupported",
                )
            )
            warnings.append(
                f"{req.name}: direct URLs, VCS and local sources are unsupported and were not fetched."
            )
            continue
        pins = [
            s.version
            for s in req.specifier
            if s.operator == "==" and "*" not in s.version
        ]
        version = (
            pins[0] if len(pins) == 1 and Version(pins[0]) in req.specifier else None
        )
        dep = _dependency(
            req.name,
            version,
            "requirements",
            True,
            str(req.marker) if req.marker else None,
            env,
        )
        dep.specifier = str(req.specifier)
        dep.extras = sorted(req.extras)
        deps.append(dep)
        if dep.version is None:
            warnings.append(
                f"{dep.name}: an exact version is missing; vulnerability status is unknown."
            )
    return Parsed(deps, [], warnings, "requirements")


def _lock(text: str, kind: str, env: dict) -> Parsed:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise InputError(f"Invalid TOML lock file: {exc}") from exc
    packages = data.get("package")
    if not isinstance(packages, list) or not packages:
        raise InputError("Lock file must contain [[package]] entries.")
    if len(packages) > MAX_DEPENDENCIES + 20:
        raise InputError(f"At most {MAX_DEPENDENCIES} package entries are supported.")
    deps: list[Dependency] = []
    warnings: list[str] = []
    edges: list[dict] = []
    roots: set[str] = set()
    root_known = False
    if kind == "uv":
        for pkg in packages:
            src = pkg.get("source", {})
            if "virtual" in src or "editable" in src:
                root_known = True
                for ref in pkg.get("dependencies", []):
                    roots.add(canonicalize_name(ref["name"]))
                for group in pkg.get("dev-dependencies", {}).values():
                    roots.update(canonicalize_name(ref["name"]) for ref in group)
        if not root_known:
            warnings.append(
                "uv.lock has no project root; direct versus transitive status is unknown."
            )
    else:
        warnings.append(
            "poetry.lock alone has no root requirements; direct versus transitive status and original version bounds are unknown."
        )
    selected: list[tuple[dict, Dependency]] = []
    for pkg in packages:
        if not isinstance(pkg, dict):
            raise InputError("Invalid lock package entry.")
        name = pkg.get("name")
        src = pkg.get("source", {})
        if kind == "uv" and ("virtual" in src or "editable" in src):
            continue
        markers = pkg.get("markers") or pkg.get("marker")
        if isinstance(markers, dict):
            markers = " or ".join(f"({x})" for x in markers.values())
        if not markers and pkg.get("resolution-markers"):
            markers = " or ".join(f"({x})" for x in pkg["resolution-markers"])
        if markers is not None and not isinstance(markers, str):
            raise InputError("Invalid environment marker in lock file.")
        dep = _dependency(
            name,
            pkg.get("version"),
            kind,
            canonicalize_name(name) in roots if root_known else None,
            markers,
            env,
        )
        registry = src.get("registry", "")
        private_source = kind == "uv" and registry not in {
            "https://pypi.org/simple",
            "https://pypi.org/simple/",
        }
        private_source |= kind == "poetry" and src.get("type") not in {None, "legacy"}
        private_source |= kind == "poetry" and src.get("url") not in {
            None,
            "https://pypi.org/simple",
            "https://pypi.org/simple/",
        }
        if private_source:
            dep.status = "unsupported"
            warnings.append(
                f"{dep.name}: a non-PyPI source cannot be mapped safely to PyPI advisories."
            )
        py = pkg.get("python-versions")
        if py and py != "*":
            try:
                from packaging.specifiers import SpecifierSet

                if Version(env["python_full_version"]) not in SpecifierSet(py):
                    dep.status = "excluded"
            except ValueError:
                warnings.append(
                    f"{dep.name}: Python constraint could not be interpreted."
                )
        if pkg.get("optional") or pkg.get("optional-dependencies"):
            warnings.append(
                f"{dep.name}: lock includes optional extras; selection is not fully known from this file."
            )
        deps.append(dep)
        selected.append((pkg, dep))
    by_name: dict[str, list[Dependency]] = {}
    for dep in deps:
        by_name.setdefault(dep.name, []).append(dep)
    for pkg, dep in selected:
        refs = pkg.get("dependencies", [])
        if isinstance(refs, dict):
            refs = [{"name": n} for n in refs]
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("name"), str):
                warnings.append(f"{dep.name}: unsupported dependency edge.")
                continue
            if marker_status(ref.get("marker"), env) == "excluded":
                continue
            candidates = [
                x
                for x in by_name.get(canonicalize_name(ref["name"]), [])
                if x.status != "excluded"
                and (not ref.get("version") or x.version == ref["version"])
            ]
            if len(candidates) == 1 and dep.status != "excluded":
                edges.append(
                    {
                        "source": dep.id,
                        "target": candidates[0].id,
                        "source_type": "lock",
                    }
                )
            else:
                warnings.append(
                    f"{dep.name} → {ref['name']}: lock edge could not be resolved uniquely."
                )
    return Parsed(deps, edges, warnings, kind)


def parse(
    filename: str, content: bytes, python_version: str = "3.11", platform: str = "linux"
) -> Parsed:
    if len(content) > MAX_BYTES:
        raise InputError("Dependency file exceeds 1 MiB.")
    safe = filename.replace("\\", "/")
    if PurePosixPath(safe).name != safe or "\x00" in safe:
        raise InputError("Filename must contain no path components.")
    env = environment(python_version, platform)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("Dependency files must be UTF-8 text.") from exc
    if "\x00" in text:
        raise InputError("Binary dependency files are unsupported.")
    if filename == "poetry.lock" or filename == "uv.lock":
        parsed = _lock(text, filename.split(".")[0], env)
    elif re.fullmatch(
        r"requirements(?:[._-][A-Za-z0-9._-]+)?\.txt", filename, re.IGNORECASE
    ):
        parsed = _requirements(text, env)
    else:
        raise InputError("Upload requirements.txt, poetry.lock or uv.lock.")
    unique: dict[tuple, Dependency] = {}
    for dep in parsed.dependencies:
        unique[(dep.name, dep.version, dep.marker, dep.source)] = dep
    parsed.dependencies = list(unique.values())
    if not parsed.dependencies:
        raise InputError("No package dependencies were found.")
    if len(parsed.dependencies) > MAX_DEPENDENCIES:
        raise InputError(f"At most {MAX_DEPENDENCIES} dependencies are supported.")
    versions: dict[str, set[str]] = {}
    for dep in parsed.dependencies:
        if dep.version and dep.status != "excluded":
            versions.setdefault(dep.name, set()).add(dep.version)
    for name, values in versions.items():
        if len(values) > 1:
            parsed.warnings.append(
                f"{name}: multiple versions may apply in this environment; scan covers each recorded version."
            )
    parsed.warnings = list(dict.fromkeys(parsed.warnings))
    return parsed
