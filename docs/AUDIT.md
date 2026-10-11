# Environment audit — 10 October 2026 (Europe/Moscow)

Observed on the user's Windows desktop, before changing project dependencies.

| Component | Functional check | Observed version | Action |
|---|---|---|---|
| Windows | .NET OS/runtime APIs | Windows 10.0.19045 x64 | Native local run |
| CPU | Process/runtime identifier | AMD64 Family 23 Model 113, 12 logical processors | Marketing model unavailable: CIM/registry denied |
| Memory | GlobalMemoryStatusEx | 15.93 GiB total; 3.16 GiB available at initial check | Avoid heavy orchestration locally |
| C: storage | Get-PSDrive | 6.10 GiB free initially | Keep dependencies and snapshots scoped to project |
| Python through PATH | python --version | 3.10.11 | Do not rely on default PATH selection |
| Python selected | py -3.11 --version and a created venv | 3.11.2 | Existing interpreter used, not reinstalled |
| Git | git --version | 2.53.0.windows.3 | Existing Git binary works |
| Node | node --version | 24.19.0 | Existing installation used |
| npm | npm --version | 11.17.0 | Existing installation used |
| PostgreSQL | explicit postgres.exe --version; new project cluster connection | 18.6 | Existing binaries; isolated cluster, 127.0.0.1:55432 |
| Docker / Compose | executable lookup and version commands | Not found | Compose supplied; execution pending |
| WSL | --status / --list --verbose | executable returned old usage; no running distro verified | WSL2 functionality unconfirmed |
| VS Code | PATH and standard user installation path | Not found at checked locations | Optional editor |
| External sources | real OSV POST and PyPI/deps.dev/EPSS GET | All four HTTP 200 | Details in API_PROBE.json |
| Local services | API HTTP, browser UI and PostgreSQL connection | Functional | Scope: localhost only |

WMI/CIM returned access denied; this is not a zero-memory/zero-disk machine. Native .NET/ctypes checks provided the hardware values above.

## Additional software

No system installation is needed for the verified native path. Backend dependencies are isolated in a Python venv; frontend dependencies are scoped to frontend/node_modules. Pinned resolved dependency files are included.

- **Docker Desktop with Compose**, a current stable version meeting the vendor's Windows support requirements: https://docs.docker.com/desktop/setup/install/windows-install/. Purpose: reproduce the Linux deployment topology. Installation can be automated via the official installer after explicit authorization; WSL/virtualization setup can require elevation/reboot. Not installed during this work. Check Windows support and sufficient disk capacity before installation.
- **WSL2**, current Microsoft release: https://learn.microsoft.com/en-us/windows/wsl/install. Purpose: Docker's Linux backend on Windows. Enabling Windows features is an administrative system change and was not attempted. `wsl --install` and a reboot are the vendor workflow after approval.
- **PostgreSQL**, existing 18.6 works. Official Windows downloads if moving machines: https://www.postgresql.org/download/windows/. No separate install needed here. Other local clusters were not inspected or changed.
- **VS Code**, current stable optional editor: https://code.visualstudio.com/download. Not required for runtime; installation has been left to the user.

Airflow, Redis and dbt are deliberately omitted from this initial operational system: the persistent PostgreSQL queue and Watch scheduler perform real scheduled incremental scans; SQL views compute analytics. No decorative services or paid resources were created.
