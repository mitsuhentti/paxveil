import argparse
import asyncio
import json
from pathlib import Path

from paxveil.config import get_settings
from paxveil.core.service import scan


def main():
    get_settings()
    parser = argparse.ArgumentParser(prog="paxveil", description="Scan a PyPI lockfile using official advisory sources")
    parser.add_argument("file", type=Path)
    parser.add_argument("--python", default="3.11")
    parser.add_argument("--platform", choices=["linux", "windows", "darwin"], default="linux")
    args = parser.parse_args()
    if not args.file.is_file() or args.file.stat().st_size > 1048576:
        parser.error("File must exist and be at most 1 MiB")
    report = asyncio.run(scan(args.file.name, args.file.read_bytes(), python_version=args.python, platform=args.platform))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("completeness") not in {"complete", "recorded_versions_checked"}:
        raise SystemExit(2)
    if report.get("findings"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
