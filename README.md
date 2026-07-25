# Python Feed Service (Artifact Feed Sync & Migration Tool)

A generic, production-ready FastAPI microservice designed to inspect, download, analyze, and publish Python wheel packages (`.whl`) to private **Azure DevOps Artifacts feeds**.

This service automates complex, multi-package dependency management tasks, such as **Python version upgrades** (e.g., upgrading repositories from Python 3.10 to 3.12 or 3.13), **security vulnerability remediations**, and **private feed synchronization**.

It is completely generic, OS-agnostic, and Python-version-agnostic—making it ideal both as a developer tool and as an API backend driven by **AI coding agents**.

---

## 🎯 Purpose & Motivation

When maintaining enterprise Python applications using private package feeds (e.g. Azure DevOps Artifacts), major upgrades or security package patches introduce significant manual overhead:

1. **Massive Package Volume**: Modern projects often depend on 90+ direct and transitive packages. Manually checking PyPI and your private feed for compatible wheels across platforms is error-prone and time-consuming.
2. **Platform & ABI Constraints**: Python version upgrades require verified wheel support for target Python tags (e.g., `cp312`, `cp311`, `py3`) and operating systems (`windows`, `linux`, `macos`). Universal pure Python wheels (`py3-none-any`) are top-priority because they work universally across operating systems and Python 3 interpreters.
3. **Transitive Dependencies**: Upgrading a top-level dependency frequently pulls in nested transitive dependencies that might not exist in your private feed yet.
4. **Feed Conflict Management**: Azure DevOps feeds reject duplicate wheel uploads with HTTP `409 Conflict`. Automatically checking the feed's PEP 503 index before running Twine uploads prevents pipeline failures.

This service eliminates these manual pain points by providing **isolated PyPI querying, feed availability checks, transitive dependency resolution, and automated batch CSV analysis and feed backfilling**.

---

## ✨ Key Capabilities

- **Generic & Configuration-Driven**: Works with **any** Azure DevOps organization, project, and private feed. No hardcoded organization or feed defaults.
- **Universal Python ABI Tag Support**: Configurable per request (e.g., `cp312`, `cp313`, `cp311`, `py3`), making it fully reusable across any Python version migration.
- **Multi-OS Platform Compatibility**: Filters and resolves wheels targeting `windows` (`win_amd64`), `linux` (`manylinux`/`x86_64`), `macos` (`macosx`/`universal2`), or `all`. Automatically detects pure universal wheels (`py3-none-any`).
- **Transitive Dependency Crawler**: Uses PyPI's JSON API to resolve inner/transitive dependencies, ensuring entire dependency trees are evaluated.
- **Batch CSV Pipeline (`/packages/analyze-and-fix`)**:
  - `ANALYZE`: Scans an input CSV and populates `pypi_index` and `feed_details` JSON columns with platform-specific wheel availability.
  - `FIX`: Downloads missing wheels from PyPI and uploads them directly to the private Azure feed using Twine.
- **Resilient Architectural Isolation**: PyPI index analysis runs independently of private feed availability. If feed credentials or network access fail, PyPI analysis continues uninterrupted.
- **Security & Redaction**: Automatically redacts Personal Access Tokens (`AZURE_PAT`) from all response logs and process outputs.

---

## 🏗 Architecture & Folder Structure

```
feed-service/
├── main.py              # FastAPI app entry point (Root & Health routes)
├── dependencies.py      # Dependency injection & domain exception mapping
├── config.py            # Environment-driven settings (pydantic-settings)
├── logger.py            # Structured logging configuration
├── models.py            # Pydantic v2 schemas with examples & descriptions
├── services.py          # PyPI, Azure Feed, and Twine upload domain logic
├── sample_upgrade.csv   # Sample CSV template for batch upgrade automation
├── .env.example         # Template for environment variables
├── pyproject.toml       # Project configuration managed via `uv`
├── Makefile             # Development workflow automation commands
├── routers/
│   ├── core.py          # Core workflow endpoints (inspect, compat-check, analyze-and-fix)
│   ├── pypi.py          # PyPI-specific wheel download endpoints
│   └── feed.py          # Azure feed information and upload endpoints
└── tests/
    └── test_api.py      # Automated offline pytest suite
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in your environment-specific Azure DevOps and feed details:

```bash
cp .env.example .env
```

Update `.env` with your Azure DevOps parameters (`AZURE_ORG`, `AZURE_PROJECT`, `AZURE_PROJECT_NAME`, `AZURE_FEED_NAME`, and `AZURE_PAT`).

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.12+
- `uv` package manager

### 2. Install Dependencies
```bash
make dev
```

### 3. Run Server
```bash
make run-reload
```
The server will start at `http://localhost:8080`.
Interactive API documentation and schema examples are accessible at `http://localhost:8080/docs`.

---

## 📡 API Endpoints Overview

| Route | Method | Router Tag | Description |
|---|---|---|---|
| `/` | `GET` | `Root` | Basic service metadata and docs link. |
| `/health` | `GET` | `Health Check` | Operational liveness check. |
| `/packages/inspect` | `POST` | `Core Feed Operations` | Inspect package release info on PyPI and target feed simultaneously. |
| `/packages/compat-check` | `POST` | `Core Feed Operations` | Bulk Python ABI / OS compatibility check for packages or `requirements.txt`. |
| `/packages/analyze-and-fix` | `POST` | `Core Feed Operations` | Single-endpoint CSV pipeline to analyze PyPI/feed status and auto-backfill missing wheels. |
| `/feed/upload-from-report` | `POST` | `Core Feed Operations` | Backfill feed using a generated compatibility CSV report. |
| `/packages/download` | `POST` | `PyPI` | Download matching `.whl` files from PyPI for target platform/Python tag. |
| `/feed/package-info` | `POST` | `Azure DevOps Feed` | Query package versions and attached wheel files in the private feed. |
| `/feed/upload` | `POST` | `Azure DevOps Feed` | Upload local wheel files to Azure feed via Twine. |

---

## 📊 Batch CSV Workflow Example (`/packages/analyze-and-fix`)

Input `sample_upgrade.csv`:
```csv
package name,current version,version to upgrade to
requests,2.28.0,latest
pydantic,1.10.0,2.6.0
```

**Request**:
```json
{
  "csv_path": "sample_upgrade.csv",
  "python_tag": "cp312",
  "platforms": ["windows", "linux"],
  "actions": ["ANALYZE", "FIX"]
}
```

**Output CSV Result**:
Columns `pypi_index`, `feed_details`, and `result` are appended in-place with detailed JSON status and completion messages:
```csv
package name,current version,version to upgrade to,pypi_index,feed_details,result
requests,2.28.0,latest,"{""cp312"": true, ""windows"": ""requests-2.31.0-py3-none-any.whl"", ""linux"": ""requests-2.31.0-py3-none-any.whl""}","{""cp312"": false, ""windows"": null, ""linux"": null}","PASS: Successfully fixed and uploaded missing wheels"
```

---

## 🛠 Development Commands

```bash
make dev        # Install runtime and dev dependencies
make run        # Start uvicorn server on port 8080
make run-reload # Start uvicorn server with auto-reload
make test       # Run test suite via pytest
make lint       # Run ruff check
make format     # Format code with ruff
make clean      # Clean virtual environment and caches
```
