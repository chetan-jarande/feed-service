# Feed Service — Single-Prompt Recreation Spec

A self-contained prompt to hand to another AI agent (with no prior knowledge) to
recreate the **AcmeHub Feed Service** exactly — capabilities, file layout,
schemas, and behaviors.

> Note: all organization/project/feed names, GUIDs and URLs below are arbitrary
> placeholders. Replace them with your own values before use.

## Purpose & context (the "why")

This service exists to support the **Python 3.12 (`cp312`) migration** of
a target application (e.g. `Acme.Sample.Api`). When upgrading to 3.12, every
dependency must have a compatible wheel available on the team's **private Azure
DevOps Artifacts feed** (`AcmeHub`). This service lets you:

- **Inspect** a package across both public **PyPI** and the private feed.
- **Check compatibility** in bulk — for a full dependency list, determine which
  packages already have `cp312` wheels for **Windows (win_amd64)** and
  **Linux (manylinux x86_64)** on the feed, and which are missing.
- **Download** the correct `cp312` x86_64 wheels from PyPI and **upload/back-fill**
  them into the feed so the 3.12 build can resolve everything privately.

This is why the defaults are `cp312`, 64-bit x86 only, and "both platforms" — they
mirror the deployment targets (Windows dev + Linux runtime). It is a developer
**tool**, run locally in-place (`uvicorn main:app`), not a distributed package.

### Environment values (the "what goes in .env")

All non-secret values have baked-in defaults (below). The **only** secret is
`AZURE_PAT` — an Azure DevOps **Personal Access Token** with **Packaging
(read / read+write)** scope, used to authenticate to the feed. It is left **empty**
in `.env.example` and must be filled in locally only; it is never committed,
logged, or returned in any response. `AZURE_PROJECT` is the Azure DevOps project
**GUID** (most reliable for the packaging APIs).

Verbatim `.env.example`:

```dotenv
# --- Azure DevOps / Artifacts ---
AZURE_ORG=contoso-devops
# Project GUID (most reliable) or project name.
AZURE_PROJECT=a1b2c3d4-0000-4444-8888-0123456789ab
AZURE_FEED_NAME=AcmeHub
AZURE_DEVOPS_UI_BASE=https://contoso-devops.visualstudio.com/Sample%20Project
AZURE_API_VERSION=7.1-preview.1
# Personal Access Token with Packaging (read / read+write) scope.
# DO NOT commit a real value — keep it only in your local .env.
AZURE_PAT=

# --- PyPI ---
PYPI_JSON_BASE=https://pypi.org/pypi
PYPI_PROJECT_BASE=https://pypi.org/project

# --- Defaults ---
DEFAULT_PYTHON_TAG=cp312
DEFAULT_DOWNLOAD_DIR=./wheels
REQUEST_TIMEOUT=60
UPLOAD_TIMEOUT=600
```

## Single-line prompt

```text
Build a Python 3.12 FastAPI microservice named "AcmeHub Feed Service" that inspects, downloads, and publishes Python wheels for a private Azure DevOps Artifacts feed (default feed "AcmeHub"), managed with `uv` and run in-place via `uvicorn main:app` (NOT packaged as a wheel), with this exact flat file layout at the project root — `main.py` (FastAPI app + routes), `services.py` (all PyPI + Azure Artifacts logic), `models.py` (Pydantic v2 request/response schemas), `config.py` (pydantic-settings env config), `logger.py` (shared stdout logger), `__init__.py`, `pyproject.toml`, `Makefile`, `.env.example`, `README.md`, and `tests/test_api.py` — where: (1) config.py defines a pydantic-settings `Settings` class (env_file=".env", extra="ignore") with fields azure_org="contoso-devops", azure_project="a1b2c3d4-0000-4444-8888-0123456789ab", azure_feed_name="AcmeHub", azure_devops_ui_base="https://contoso-devops.visualstudio.com/Sample%20Project", azure_api_version="7.1-preview.1", azure_pat="" (the only secret), pypi_json_base="https://pypi.org/pypi", pypi_project_base="https://pypi.org/project", default_python_tag="cp312", default_download_dir="./wheels", request_timeout=60, upload_timeout=600, plus computed properties feeds_api_base (`https://feeds.dev.azure.com/{org}/{project}/_apis/packaging/Feeds`), upload_url(feed) (`https://pkgs.dev.azure.com/{org}/{project}/_packaging/{feed}/pypi/upload/`), simple_index_url(feed) (`.../pypi/simple/`), and an `@lru_cache get_settings()`; (2) logger.py configures logging.basicConfig to stdout at INFO with format "[%(asctime)s] %(levelname)s <%(module)s:%(funcName)s:%(lineno)d> %(message)s" and exposes `get_logger(name)`; (3) services.py defines three domain exceptions NotFoundError/BadRequestError/UpstreamError and a `FeedService(settings)` class using Basic auth (base64 of `:{pat}`) for the feed and anonymous requests for PyPI, with helpers to normalize names (collapse `-_.` to `-`, lowercase), parse versions via `packaging.version.Version` (fallback "0"), query the feed packaging REST API by trying multiple name spellings (dots vs dashes) and matching on normalized name, list a version's files, build feed overview URLs, and read already-published filenames from the feed's PEP 503 simple index via regex; and implements the methods: `inspect(name, feed)` returning latest PyPI details (name/version/summary/project_url/release_url) AND feed current-version+URL, each with independent error capture (404 only if BOTH missing); `download_wheels(name, version, platform, python_tag, dest_dir)` that fetches PyPI release files and selects wheels by a static `_select_wheels` rule — always accept pure `py3-none-any` wheels, match python_tag substring or `abi3`, restrict to 64-bit x86 only (Linux manylinux/linux_x86_64 with x86_64, Windows win_amd64), platform ∈ {both,windows,linux} — then stream-downloads to dest_dir returning filename/abspath/size; `upload_wheels(whl_paths, feed, skip_existing=True)` that validates PAT presence (BadRequestError if missing), file existence, and `.whl/.tar.gz/.zip` extensions, pre-filters against the feed simple index when skip_existing (because Azure returns 409 on duplicates and twine's --skip-existing is unsupported), then runs `python -m twine upload --repository-url {upload_url} --username __token__ --password {pat} --non-interactive --disable-progress-bar {files}` via subprocess with upload_timeout, ALWAYS redacting the PAT from output (replace with "***"), raising UpstreamError on failure/twine-missing/timeout; `compat_check(packages, requirements_path, feed, dest_csv, include_pypi)` that parses `name==version` specs (or bare name=>latest, dedup on normalized name+version, skipping comments and `-` lines) from the list and/or a requirements file, and for each computes a cp312 compatibility row via `_wheel_flags` (classify filenames into pure/win/linux/sdist, abi3 counts as cp312, exclude musllinux) comparing feed vs PyPI to set per-platform `feed_upload_needed_windows/linux` and a classification of "OK"/"NEEDS FEED UPLOAD"/"SDIST ONLY"/"NEEDS WHEEL REBUILD" with notes, optionally writing a CSV with fields [package,version,pure_py3_none_any,cp312_win_amd64,cp312_manylinux,feed_upload_needed_windows,feed_upload_needed_linux,classification,notes]; and `upload_from_report(csv_path, feed, dry_run=True, dest_dir)` that reads such a CSV, builds an upload plan for rows flagged needed (platform derived from which flags are yes), and when not dry_run downloads the cp312 wheels from PyPI and uploads them via upload_wheels, returning planned/uploaded/skipped/unavailable; (4) models.py defines a `Platform(str, Enum)` {both,windows,linux} and Pydantic v2 request models InspectRequest(name required min_length=1, feed_name?), DownloadRequest(name, version?, platform=both, python_tag?, dest_dir?), FeedInfoRequest(name, feed_name?, version?), UploadRequest(whl_paths required min_length=1, feed_name?, skip_existing=True), CompatCheckRequest(packages=[], requirements_path?, feed_name?, dest_csv?, include_pypi=True), UploadFromReportRequest(csv_path required, feed_name?, dry_run=True, dest_dir?), plus matching response models PypiDetails, FeedRef, InspectResponse, DownloadedFile, DownloadResponse, FeedInfoResponse, UploadResponse, CompatRow, CompatCheckResponse, UploadFromReportResponse; (5) main.py creates `app = FastAPI(title="AcmeHub Feed Service", version="1.0.0", description=...)`, wires `Settings`/`FeedService` via Depends, uses a `_run` wrapper mapping NotFoundError→404, BadRequestError→400, UpstreamError→502 (and letting FastAPI return 422 for schema validation), and exposes GET `/health` ({"status":"ok"}) plus POST endpoints `/packages/inspect`, `/packages/download`, `/feed/package-info`, `/feed/upload`, `/packages/compat-check`, `/feed/upload-from-report` (each defaulting feed to settings.azure_feed_name when unset); (6) pyproject.toml sets requires-python ">=3.12", `[tool.uv] package=false`, runtime deps fastapi>=0.110, uvicorn[standard]>=0.29, requests>=2.31, packaging>=23.0, pydantic>=2.6, pydantic-settings>=2.2, twine>=5.0, dev group pytest>=8/httpx>=0.27/ruff>=0.5/mypy>=1.10, ruff line-length 120, mypy ignore_missing_imports, and pytest pythonpath=["."] testpaths=["tests"]; (7) Makefile with uv-based targets venv/deps/dev/run/run-reload/test/lint/format/clean/help (defaults PYTHON_VERSION=3.12, HOST=0.0.0.0, PORT=8080, run-reload on 8080); (8) .env.example listing all non-secret env vars with AZURE_PAT left empty; and (9) tests/test_api.py using fastapi.testclient TestClient to cover /health, empty-name 422 validation, upload missing-file 400 (with a dummy PAT and get_settings.cache_clear), empty whl_paths 422, and `_select_wheels` behavior for both/linux/python-tag filtering (excluding aarch64 and sdists) — all tests fully offline with no network calls; ensure the AZURE_PAT is never logged or returned in any response.
```

## Quick reference — endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness check. |
| `/packages/inspect` | POST | Latest version from **both** PyPI and the feed, with links. |
| `/packages/download` | POST | Download `.whl` file(s) from PyPI (Windows + Linux, x86_64). |
| `/feed/package-info` | POST | Current + all in-feed versions + wheels (**feed only**). |
| `/feed/upload` | POST | Upload local `.whl` file(s) to the feed via `twine`. |
| `/packages/compat-check` | POST | Bulk cp312 compatibility matrix (feed + PyPI), optional CSV. |
| `/feed/upload-from-report` | POST | Upload cp312 wheels flagged as needed in a compat-check CSV. |

## Error-code mapping

| Status | When |
|---|---|
| `422` | Schema validation (missing/empty `name`, empty `whl_paths`, bad `platform`). |
| `400` | Valid-looking input that fails at runtime (missing file, non-distributable). |
| `404` | Package / version / feed not found. |
| `502` | PyPI, the feed, or `twine` failed. |

## Target file layout

```
feed-service/
├── main.py           # FastAPI app + routes
├── services.py       # PyPI + Azure Artifacts feed logic
├── models.py         # Pydantic request/response schemas
├── config.py         # Env-driven settings (pydantic-settings)
├── logger.py         # Shared stdout logger (get_logger)
├── __init__.py
├── tests/
│   └── test_api.py   # Offline tests
├── pyproject.toml    # Dependencies (uv)
├── Makefile          # Dev workflow
├── .env.example      # Configuration template
└── README.md
```

## Per-file contents (functions, classes & symbols)

### `config.py`
- **`Settings(BaseSettings)`** — `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`.
  - Fields: `azure_org`, `azure_project`, `azure_feed_name`, `azure_devops_ui_base`, `azure_api_version`, `azure_pat`, `pypi_json_base`, `pypi_project_base`, `default_python_tag`, `default_download_dir`, `request_timeout`, `upload_timeout`.
  - `@property feeds_api_base` → `https://feeds.dev.azure.com/{org}/{project}/_apis/packaging/Feeds`
  - `upload_url(feed_name)` → `https://pkgs.dev.azure.com/{org}/{project}/_packaging/{feed}/pypi/upload/`
  - `simple_index_url(feed_name)` → `https://pkgs.dev.azure.com/{org}/{project}/_packaging/{feed}/pypi/simple/`
- **`@lru_cache get_settings() -> Settings`**

### `logger.py`
- Module-level `logging.basicConfig(level=INFO, stream=sys.stdout, format="[%(asctime)s] %(levelname)s <%(module)s:%(funcName)s:%(lineno)d> %(message)s")`
- **`get_logger(name: str) -> logging.Logger`**

### `models.py`
- **`Platform(str, Enum)`** → `both`, `windows`, `linux`
- Requests: **`InspectRequest`**, **`DownloadRequest`**, **`FeedInfoRequest`**, **`UploadRequest`**, **`CompatCheckRequest`**, **`UploadFromReportRequest`**
- Responses: **`PypiDetails`**, **`FeedRef`**, **`InspectResponse`**, **`DownloadedFile`**, **`DownloadResponse`**, **`FeedInfoResponse`**, **`UploadResponse`**, **`CompatRow`**, **`CompatCheckResponse`**, **`UploadFromReportResponse`**

### `services.py`
- Exceptions: **`NotFoundError`**, **`BadRequestError`**, **`UpstreamError`**
- Module helpers: **`_norm(name)`** (collapse `-_.`→`-`, lowercase), **`_vkey(v)`** (`Version`, fallback `"0"`)
- **`FeedService`** class:
  - `__init__(self, settings)`
  - `_auth_header()` — Basic auth, base64 of `:{pat}`
  - `_get(url, auth)` — HTTP GET wrapper → `UpstreamError` on failure
  - `pypi_info(name)`, `pypi_latest(name)`
  - `_feed_query(feed, query)`, `find_feed_package(name, feed)` (tries 4 name spellings), `feed_version_files(feed, pkg_id, ver_id)`, `feed_overview_url(feed, name, version)`, `feed_existing_filenames(feed, package_name)` (PEP 503 index regex)
  - `feed_package_info(name, feed, version=None)`
  - `inspect(name, feed)`
  - `@staticmethod _select_wheels(files, platform, python_tag)`
  - `download_wheels(name, version, platform, python_tag, dest_dir)`
  - `upload_wheels(whl_paths, feed, skip_existing=True)`
  - Class attr `CSV_FIELDS` (9 columns)
  - `@staticmethod _wheel_flags(filenames, version)`, `_pypi_flags(name, version)`, `compat_row(name, version, feed, include_pypi)`
  - `@staticmethod _parse_specs(packages, requirements_path)`
  - `compat_check(packages, requirements_path, feed, dest_csv, include_pypi)`
  - `upload_from_report(csv_path, feed, dry_run, dest_dir)`

### `main.py`
- `app = FastAPI(title="AcmeHub Feed Service", version="1.0.0", description=...)`
- **`get_service(settings=Depends(get_settings)) -> FeedService`**
- **`_run(fn)`** — maps `NotFoundError`→404, `BadRequestError`→400, `UpstreamError`→502
- Route handlers: **`health`**, **`inspect_package`**, **`download_package`**, **`feed_package_info`**, **`feed_upload`**, **`compat_check`**, **`upload_from_report`**

### `tests/test_api.py`
- `client = TestClient(main.app)`
- **`test_health`**, **`test_inspect_validation_error`**, **`test_upload_missing_file_is_bad_request(monkeypatch)`**, **`test_upload_requires_at_least_one_path`**, **`test_select_wheels_both_platforms`**, **`test_select_wheels_linux_excludes_windows`**, **`test_select_wheels_python_tag_filter`**

## Makefile targets

| Target | Command | Description |
|---|---|---|
| `venv` | `uv venv --python $(PYTHON_VERSION) $(VENV_ROOT)` | Create the uv virtual environment. |
| `deps` | `uv sync --no-dev` | Install runtime dependencies only. |
| `dev` | `uv sync` | Install runtime + dev dependencies. |
| `run` | `uv run uvicorn main:app --host $(HOST) --port $(PORT)` | Start the API server. |
| `run-reload` | `uv run uvicorn main:app --reload --port $(PORT)` | Start with auto-reload. |
| `test` | `uv run pytest -vvv` | Run the test suite. |
| `lint` | `uv run ruff check .` | Run ruff checks. |
| `format` | `uv run ruff format .` | Auto-format with ruff. |
| `clean` | remove `__pycache__`, `.venv`, `.pytest_cache`, `.ruff_cache` | Remove caches + venv. |
| `help` | grep `## ` lines | Show help (also `.DEFAULT_GOAL`). |

Variables: `PYTHON_VERSION ?= 3.12`, `VENV_ROOT ?= ./.venv`, `HOST ?= 0.0.0.0`, `PORT ?= 8080`. `.PHONY` lists all targets.

## `.env` keys

| Key | Default | Secret? | Description |
|---|---|---|---|
| `AZURE_ORG` | `contoso-devops` | no | Azure DevOps organization. |
| `AZURE_PROJECT` | `a1b2c3d4-0000-4444-8888-0123456789ab` | no | Project **GUID** (or name). |
| `AZURE_FEED_NAME` | `AcmeHub` | no | Default feed. |
| `AZURE_DEVOPS_UI_BASE` | `https://contoso-devops.visualstudio.com/Sample%20Project` | no | Base for feed overview URLs. |
| `AZURE_API_VERSION` | `7.1-preview.1` | no | Artifacts REST API version. |
| `AZURE_PAT` | *(empty)* | **YES** | PAT with Packaging (read/read+write) scope. |
| `PYPI_JSON_BASE` | `https://pypi.org/pypi` | no | PyPI JSON API base. |
| `PYPI_PROJECT_BASE` | `https://pypi.org/project` | no | PyPI project page base. |
| `DEFAULT_PYTHON_TAG` | `cp312` | no | Default ABI/python tag. |
| `DEFAULT_DOWNLOAD_DIR` | `./wheels` | no | Default download directory. |
| `REQUEST_TIMEOUT` | `60` | no | HTTP timeout (s). |
| `UPLOAD_TIMEOUT` | `600` | no | twine upload timeout (s). |

## Endpoint details (request → response)

### `GET /health`
- Request: none. Response: `{"status": "ok"}`.

### `POST /packages/inspect` → `InspectResponse`
- Request `InspectRequest`: `name` (required, min_length=1), `feed_name?`.
- Response: `name`, `pypi` (`PypiDetails` | null), `pypi_error?`, `feed` (`FeedRef` | null), `feed_error?`. Returns 404 only if **both** PyPI and feed miss.

### `POST /packages/download` → `DownloadResponse`
- Request `DownloadRequest`: `name` (required), `version?` (default latest on PyPI), `platform` (`both`|`windows`|`linux`, default `both`), `python_tag?` (default `cp312`), `dest_dir?` (default `./wheels`).
- Response: `name`, `version`, `platform`, `python_tag`, `dest_dir`, `files[]` (`DownloadedFile`: `filename`, `path`, `size`).

### `POST /feed/package-info` → `FeedInfoResponse`
- Request `FeedInfoRequest`: `name` (required), `feed_name?`, `version?`.
- Response: `name`, `feed_name`, `current_version?`, `current_version_url?`, `available_versions[]`, `target_version?`, `wheels[]`.

### `POST /feed/upload` → `UploadResponse`
- Request `UploadRequest`: `whl_paths[]` (required, min_length=1), `feed_name?`, `skip_existing` (default `true`).
- Response: `feed_name`, `uploaded[]`, `skipped[]`, `skip_existing`, `output` (PAT redacted as `***`).

### `POST /packages/compat-check` → `CompatCheckResponse`
- Request `CompatCheckRequest`: `packages[]` (specs `name==version` or bare `name`), `requirements_path?`, `feed_name?`, `dest_csv?`, `include_pypi` (default `true`).
- Response: `feed_name`, `total`, `needs_upload`, `csv_path?`, `rows[]` (`CompatRow`: `package`, `version?`, `pure_py3_none_any`, `cp312_win_amd64`, `cp312_manylinux`, `feed_upload_needed_windows`, `feed_upload_needed_linux`, `classification`, `notes`).
- Classifications: `OK` / `NEEDS FEED UPLOAD` / `SDIST ONLY` / `NEEDS WHEEL REBUILD`.

### `POST /feed/upload-from-report` → `UploadFromReportResponse`
- Request `UploadFromReportRequest`: `csv_path` (required), `feed_name?`, `dry_run` (default `true`), `dest_dir?`.
- Response: `feed_name`, `dry_run`, `planned[]`, `uploaded[]`, `skipped[]`, `unavailable[]`, `output`.
