import httpx
import pytest

from paxveil.core import service
from paxveil.core.advisories import affected_version, deduplicate, prioritize, score
from paxveil.core.fixlab import candidates
from paxveil.core.sources import SnapshotCache, Sources

ADVISORY = {
    "id": "GHSA-fixture",
    "aliases": ["CVE-2024-12345"],
    "summary": "Controlled test advisory",
    "severity": [
        {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}
    ],
    "affected": [
        {
            "package": {"name": "fixture-package", "ecosystem": "PyPI"},
            "ranges": [
                {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2"}]}
            ],
        }
    ],
}


def source_factory(monkeypatch, tmp_path, handler):
    monkeypatch.setattr(
        service,
        "Sources",
        lambda **kwargs: Sources(
            cache=SnapshotCache(tmp_path),
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )


@pytest.mark.asyncio
async def test_scan_uses_real_api_shapes_and_explicit_unknowns(monkeypatch, tmp_path):
    def handler(request):
        host, path = request.url.host, request.url.path
        if host == "pypi.org":
            return httpx.Response(
                200, json={"info": {"requires_dist": []}, "urls": [{}]}
            )
        if host == "api.deps.dev":
            return httpx.Response(200, json={"pypi": {"dependencies": []}})
        if path.endswith("querybatch"):
            return httpx.Response(
                200, json={"results": [{"vulns": [{"id": "GHSA-fixture"}]}]}
            )
        if host == "api.osv.dev":
            return httpx.Response(200, json=ADVISORY)
        if host == "api.first.org":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"cve": "CVE-2024-12345", "epss": "0.125", "date": "2026-10-09"}
                    ]
                },
            )
        return httpx.Response(404)

    source_factory(monkeypatch, tmp_path, handler)
    result = await service.scan(
        "requirements.txt", b"fixture-package==1\nunresolved>=2\n"
    )
    finding = result["findings"][0]
    assert finding["cvss"] == 9.8
    assert finding["epss"] == 0.125
    assert finding["kev"] is None
    assert finding["fixed_versions"] == ["2"]
    assert result["completeness"] == "partial"
    assert result["vulnerability_lookup_complete"] is False
    assert result["dependencies"][1]["version"] is None


@pytest.mark.asyncio
async def test_osv_failure_is_not_a_clean_report(monkeypatch, tmp_path):
    def handler(request):
        if request.url.host == "api.osv.dev":
            return httpx.Response(400)
        return httpx.Response(200, json={"info": {}, "pypi": {}})

    source_factory(monkeypatch, tmp_path, handler)
    result = await service.scan("requirements.txt", b"fixture-package==1\n")
    assert result["findings"] == []
    assert result["completeness"] == "partial"
    assert any("not a clean result" in warning for warning in result["warnings"])
    assert result["vulnerability_lookup_complete"] is False


@pytest.mark.asyncio
async def test_malformed_osv_response_is_not_lookup_complete(monkeypatch, tmp_path):
    def handler(request):
        if request.url.host == "api.osv.dev":
            return httpx.Response(200, json={"results": [None]})
        return httpx.Response(200, json={"info": {}, "pypi": {}})

    source_factory(monkeypatch, tmp_path, handler)
    result = await service.scan("requirements.txt", b"fixture-package==1\n")
    assert result["findings"] == []
    assert result["vulnerability_lookup_complete"] is False
    assert result["completeness"] == "partial"
    assert any(
        source["name"] == "OSV" and source["status"] == "ok"
        for source in result["sources"]
    )


@pytest.mark.asyncio
async def test_valid_empty_osv_response_is_lookup_complete(monkeypatch, tmp_path):
    def handler(request):
        if request.url.host == "api.osv.dev":
            return httpx.Response(200, json={"results": [{}]})
        return httpx.Response(200, json={"info": {}, "pypi": {}})

    source_factory(monkeypatch, tmp_path, handler)
    result = await service.scan("requirements.txt", b"fixture-package==1\n")
    assert result["findings"] == []
    assert result["vulnerability_lookup_complete"] is True


@pytest.mark.asyncio
async def test_invalid_advisory_details_is_not_lookup_complete(monkeypatch, tmp_path):
    def handler(request):
        if request.url.path.endswith("querybatch"):
            return httpx.Response(
                200, json={"results": [{"vulns": [{"id": "GHSA-fixture"}]}]}
            )
        if request.url.host == "api.osv.dev":
            return httpx.Response(200, json={"affected": []})
        return httpx.Response(200, json={"info": {}, "pypi": {}})

    source_factory(monkeypatch, tmp_path, handler)
    result = await service.scan("requirements.txt", b"fixture-package==1\n")
    assert result["vulnerability_lookup_complete"] is False


@pytest.mark.asyncio
async def test_nonexistent_release_is_never_claimed_vulnerable(monkeypatch, tmp_path):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(404)

    source_factory(monkeypatch, tmp_path, handler)
    result = await service.scan("requirements.txt", b"fixture-package==0.0.999999\n")
    assert result["dependencies"][0]["status"] == "version_not_found"
    assert not any("api.osv.dev" in url for url in urls)


@pytest.mark.parametrize(
    "version,status",
    [(None, "possible"), ("1.9", "confirmed"), ("2", "no_match"), ("3", "no_match")],
)
def test_affected_ranges(version, status):
    assert affected_version(ADVISORY, "fixture-package", version) == status


def test_cvss_and_priority_distinguish_probability():
    assert score(ADVISORY) == (9.8, "critical")
    priority, reasons = prioritize(9.8, "critical", 0.125, True, True)
    assert priority == 81
    assert any("not proof" in reason for reason in reasons)


def test_malformed_cvss_remains_unknown():
    assert score({"severity": [{"type": "CVSS_V3", "score": "garbage"}]}) == (
        None,
        "unknown",
    )


def test_alias_deduplication_merges_evidence():
    def finding(identity, aliases):
        return {
            "id": identity,
            "aliases": aliases,
            "package": "a",
            "version": "1",
            "cvss": None,
            "priority": 10,
            "references": [],
            "fixed_versions": [],
        }

    rows = deduplicate(
        [finding("PYSEC-a", ["CVE-2024-12345"]), finding("GHSA-b", ["CVE-2024-12345"])]
    )
    assert len(rows) == 1
    assert "PYSEC-a" in rows[0]["aliases"]


def test_candidates_filter_yanks_python_and_bounds():
    def wheel(**kwargs):
        return {"packagetype": "bdist_wheel", "requires_python": ">=3.8", **kwargs}

    metadata = {
        "releases": {
            "1.2.1": [wheel()],
            "1.2.2": [wheel(yanked=True)],
            "1.3": [wheel()],
            "2": [wheel()],
            "3": [wheel(requires_python=">=3.12")],
            "4rc1": [wheel()],
        }
    }
    assert candidates(metadata, "1.2", "3.11", ">=1,<2", "Minimal Change") == ["1.2.1"]
    assert candidates(metadata, "1.2", "3.11", ">=1,<2", "Balanced") == ["1.3", "1.2.1"]
    assert candidates(metadata, "1.2", "3.11", ">=1,<2", "Maximum Coverage")[0] == "2"


@pytest.mark.asyncio
async def test_fire_propagates_confirmed_and_unknown_version_matches(
    monkeypatch, tmp_path
):
    source_factory(
        monkeypatch, tmp_path, lambda request: httpx.Response(200, json=ADVISORY)
    )
    reports = [
        {
            "project_id": 7,
            "project_name": "controlled",
            "dependencies": [
                {"name": "fixture-package", "version": "1", "status": "active"},
                {"name": "fixture-package", "version": None, "status": "unresolved"},
            ],
            "findings": [{"id": "GHSA-fixture", "aliases": ["CVE-2024-12345"]}],
        }
    ]
    result = await service.fire("CVE-2024-12345", reports)
    assert result["status"] == "confirmed"
    assert {row["status"] for row in result["matches"]} == {"confirmed", "possible"}
