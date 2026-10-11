"""Opt-in public API checks; controlled advisory fixtures live in other tests."""

import os

import pytest

from paxveil.core.service import fire, scan

pytestmark = pytest.mark.skipif(
    os.getenv("PAXVEIL_LIVE_TESTS") != "1",
    reason="Set PAXVEIL_LIVE_TESTS=1 for non-aggressive official public API verification.",
)


@pytest.mark.asyncio
async def test_real_osv_pypi_and_cve_match():
    report = await scan("requirements.txt", b"requests==2.31.0\n")
    assert any(
        row["package"] == "requests" and "CVE-2024-35195" in row["aliases"]
        for row in report["findings"]
    )
    assert any(
        source["name"] == "OSV" and source["status"] in {"ok", "cached"}
        for source in report["sources"]
    )
    result = await fire(
        "CVE-2024-35195",
        [
            {
                **report,
                "project_id": "live",
                "project_name": "Official public requests version",
            }
        ],
    )
    assert result["status"] == "confirmed"
    assert result["matches"][0]["version"] == "2.31.0"


@pytest.mark.asyncio
async def test_real_package_with_no_known_osv_matches():
    report = await scan("requirements.txt", b"sampleproject==4.0.0\n")
    assert report["findings"] == []
    assert report["completeness"] == "recorded_versions_checked"
