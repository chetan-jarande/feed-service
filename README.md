# AcmeHub Feed Service

A professional, FastAPI-based microservice that inspects, downloads, and publishes Python wheels for a private Azure DevOps Artifacts feed (`AcmeHub`). Designed specifically to automate large-scale Python version migrations (e.g., Python 3.10 to 3.12 or 3.13) and security audits by providing deep insights and automated backfill operations for private feeds.

Built as an API-first tool, it acts as an intelligent intermediary that can be queried programmatically or driven by an AI coding agent to resolve missing transitive dependencies.

## Key Capabilities

- **Universal Python Tag Support**: Supports dynamic `python_tag` resolution (`cp312`, `cp313`, `py3`, etc.) ensuring your tools aren't hardcoded to a specific Python version migration.
- **Transitive Dependency Resolution**: Automatically crawls PyPI to discover inner/transitive dependencies when verifying compatibility, ensuring 90+ package trees are fully satisfied.
- **Cross-Platform Wheel Filtering**: Validates and downloads wheels specifically targeting OS requirements (`windows`, `linux`, `macos`, or `all`). Automatically prioritizes universal pure Python wheels (`py3-none-any`).
- **Deep Compatibility Checks (`/packages/compat-check`)**: Evaluates `requirements.txt` against both PyPI and Azure DevOps feeds, reporting exactly which platforms are satisfied and which need backfilling.
- **Automated Upload Pipeline (`/feed/upload-from-report`)**: Reads the output of a compatibility check and securely triggers `twine` uploads to backfill the exact missing `.whl` files into the private feed.

## Quick Start

### 1. Requirements
- Python 3.12+
- `uv` package manager

### 2. Setup Environment
```bash
cp .env.example .env
# Edit .env and set your AZURE_PAT if performing upload actions
```

### 3. Install Dependencies
```bash
make dev
```

### 4. Run Service
```bash
make run-reload
```
The API server runs at `http://localhost:8080`. Interactive API documentation and schema models are available at `http://localhost:8080/docs`.

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness check. |
| `/packages/inspect` | POST | Detailed latest version info from PyPI and the feed. |
| `/packages/download` | POST | Download `.whl` files from PyPI matching `python_tag` and `platform`. |
| `/feed/package-info` | POST | Query feed package versions and attached wheel files. |
| `/feed/upload` | POST | Securely upload local `.whl` files to the Azure DevOps feed. |
| `/packages/compat-check` | POST | Generate a robust cp/py compatibility report, optionally resolving transitive dependencies. |
| `/feed/upload-from-report` | POST | Automatically download and upload wheels flagged as missing in a CSV report. |

## Development Commands

```bash
make dev        # Install dependencies
make run        # Run server on port 8080
make test       # Run pytest test suite
make lint       # Run ruff lint check
make format     # Format code with ruff
make clean      # Clean virtual environment and caches
```
