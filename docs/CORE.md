# Scanning, Fire Drill and FixLab

PAXVEIL parses uploaded text without installing packages, executing build backends, evaluating Python or following file includes, index directives, VCS URLs or local paths. Accepted files are bounded to 1 MiB and 300 dependency rows. Package names are normalized according to PyPI rules. Only exact PEP 440 versions are queried; unresolved requirements remain visible with an unknown result.

Environment markers use the user's selected Python version and operating system. Markers requiring machine or kernel information remain uncertain. A Poetry lock file alone does not identify project roots; root status is null and FixLab reports that it cannot faithfully resolve that project. A uv lock file's virtual project entry supplies root dependencies. Optional groups and extras not established by the file are documented as limitations.

The API clients use asynchronous HTTP, bounded connections, per-host pacing, 8-second connection and 20-second request timeouts, at most three attempts with backoff, and no redirects. Only fixed HTTPS source hosts are allowed. Official responses are stored in a TTL cache and immutable content-addressed snapshots in `PAXVEIL_CACHE_DIR/sources.sqlite3`. Reports retain source times and snapshot hashes. A failed refresh never silently falls back to stale results. OSV failures produce partial reports, rather than a false clean result.

`vulnerability_lookup_complete` records successful validation of all applicable exact-version OSV queries and advisory details. Unresolved, unsupported or uncertain recorded dependencies make it false. An HTTP 200 response with an invalid shape does not set it true. Enrichment or independent metadata cross-check outages can make the overall report partial while this OSV-specific field remains true. The cache index keeps the most recent fetch timestamp independently of the immutable snapshot's first-fetch timestamp, including when a refetch returns identical content.

## Official sources

- [OSV API](https://google.github.io/osv.dev/api/): package/version batch queries, pagination and advisory records; aliases deduplicate records for the same package version.
- [PyPI JSON API](https://docs.pypi.org/api/json/): recorded release existence, Requires-Python, Requires-Dist and stable wheel releases. The project-level releases field is currently deprecated; migration to the index API is recorded as a maintenance requirement.
- [deps.dev v3](https://docs.deps.dev/api/v3/): independent requirements metadata cross-check for up to ten recorded releases. Its generic Linux resolution is not substituted for the uploaded project's graph.
- [FIRST EPSS API](https://api.first.org/epss/): current CVE exploitation probabilities and score dates. Probabilities remain null if no score exists or the source is unavailable.
- [CISA KEV JSON feed](https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json): evidence of exploitation in the wild. Missing source data leaves KEV null.

## Explainable priority

PAXVEIL's triage policy adds impact (CVSS × 5, up to 50), FIRST EPSS × 20, CISA KEV evidence (25) and recorded root status (5), capped at 100. If CVSS is absent, source severity contributes a disclosed policy weight. Each finding contains the components and uncertainty explanations. This policy score is distinct from EPSS and never claims application reachability or exploitability.

## FixLab

Minimal Change considers the smallest newer stable release in the current major/minor family. Balanced considers the newest stable release in the current major family. Both preserve recorded bounds other than the exact current pin. Maximum Coverage considers newer major versions and explicitly relaxes these bounds. All proposals first verify real, non-yanked PyPI wheel releases with a compatible Python declaration.

The resolver uses [`uv pip compile`](https://docs.astral.sh/uv/pip/compile/) with `--only-binary :all:` (the documented equivalent of `--no-build`), `--no-config`, no interpreter downloads and a dedicated temporary cache. No installation occurs. The subprocess runs through a local CONNECT proxy permitting only TLS connections to `pypi.org` and `files.pythonhosted.org`; malicious direct URLs in wheel metadata are blocked. Input requirements are reconstructed from validated names, extras and exact versions. Subprocess execution has a 90-second limit, bounded diagnostic output and a network transfer limit. Windows uses file-backed diagnostics to avoid sandbox named-pipe restrictions.

Each successfully resolved environment is scanned against OSV again. Before/after counts and graph changes come from those reports. A conflict or missing metadata yields no fabricated after count. A successful resolution establishes metadata compatibility, not behavioral compatibility; application tests are never run.

## Fire Drill

A validated CVE is queried directly in OSV and through advisory aliases already known in saved reports. PyPI package names, exact versions, affected ranges and graph paths establish confirmed or possible matches. Missing CVE coverage is insufficient data, not proof that a project is unaffected. A recorded version match does not establish reachability.

## Verified behavior

`CORE_VALIDATION.json` contains genuine public-source responses summarized into real reports. The public vulnerable requirements example contained 12 deduplicated findings in five recorded dependencies at verification time. Balanced and Maximum Coverage resolved five packages and subsequent OSV scans returned zero known findings. Minimal Change had no qualifying proposal; this is reported as insufficient data. A `sampleproject==4.0.0` scan returned zero known OSV findings with successful recorded-version coverage. Fire Drill found a confirmed CVE match. These observations are time-specific and may change as sources publish new records.

Unit tests use deliberately controlled fixtures, separate from these live reports. Opt-in public integration checks run with `PAXVEIL_LIVE_TESTS=1`.

## Limitations and maintenance

The scanner cannot infer installed transitive versions absent from the uploaded file, runtime reachability, application configuration, selected optional groups or machine architecture. Requirements entries are treated as simulation roots because a plain file does not establish original direct/transitive intent. The resolver targets x86_64. Poetry requires an additional project manifest for faithful FixLab root constraints, so this version refuses to manufacture them. Public metadata availability and rate behavior can limit completeness. Historical snapshots require a future retention policy for long-lived deployments. The package inventory is not a license audit or full SBOM.
