from enum import Enum

from pydantic import BaseModel, Field


class Platform(str, Enum):
    all = "all"
    windows = "windows"
    linux = "linux"
    macos = "macos"

class ActionType(str, Enum):
    ANALYZE = "ANALYZE"
    FIX = "FIX"


# --- Request Models ---


class InspectRequest(BaseModel):
    name: str = Field(..., min_length=1, description="The PyPI package name to inspect.")
    feed_name: str | None = Field(default=None, description="Optional target feed name. Defaults to the environment setting.")


class DownloadRequest(BaseModel):
    name: str = Field(..., min_length=1, description="The PyPI package name to download.")
    version: str | None = Field(default=None, description="The specific version to download. Defaults to the latest on PyPI.")
    platform: Platform = Field(default=Platform.all, description="The target OS platform(s).")
    python_tag: str | None = Field(default="cp312", description="The Python ABI tag to filter wheels by (e.g. cp312, cp311).")
    dest_dir: str | None = Field(default=None, description="Local directory to download the wheels into.")


class FeedInfoRequest(BaseModel):
    name: str = Field(..., min_length=1, description="The package name to query in the Azure feed.")
    feed_name: str | None = Field(default=None, description="Optional target feed name.")
    version: str | None = Field(default=None, description="Specific version to query. Defaults to the latest available in the feed.")


class UploadRequest(BaseModel):
    whl_paths: list[str] = Field(..., min_length=1, description="List of local file paths (.whl, .tar.gz, .zip) to upload.")
    feed_name: str | None = Field(default=None, description="Optional target feed name.")
    skip_existing: bool = Field(default=True, description="If true, checks the feed's simple index and skips files that are already present.")


class CompatCheckRequest(BaseModel):
    packages: list[str] = Field(default_factory=list, description="List of package specifications (e.g., 'requests==2.31.0' or 'numpy').")
    requirements_path: str | None = Field(default=None, description="Path to a requirements.txt file to parse.")
    feed_name: str | None = Field(default=None, description="Optional target feed name.")
    dest_csv: str | None = Field(default=None, description="Path to write the output report as a CSV file.")
    include_pypi: bool = Field(default=True, description="Whether to fall back to checking PyPI if the feed doesn't satisfy requirements.")
    python_tag: str = Field(default="cp312", description="The Python ABI tag to evaluate compatibility against (e.g. cp312).")
    resolve_dependencies: bool = Field(default=False, description="If true, queries PyPI to resolve and evaluate transitive dependencies.")


class UploadFromReportRequest(BaseModel):
    csv_path: str = Field(..., min_length=1, description="Path to the generated compatibility CSV report.")
    feed_name: str | None = Field(default=None, description="Optional target feed name.")
    dry_run: bool = Field(default=True, description="If true, only prints what would be downloaded and uploaded without taking action.")
    dest_dir: str | None = Field(default=None, description="Directory to download wheels into temporarily before upload.")
    python_tag: str = Field(default="cp312", description="The Python ABI tag used for downloading missing wheels.")


class AnalyzeAndFixRequest(BaseModel):
    csv_path: str = Field(..., min_length=1, description="Path to the local CSV file to process.")
    python_tag: str = Field(default="py312", description="Python version compatibility tag, e.g. py312 or cp312.")
    platforms: list[str] = Field(default_factory=lambda: ["windows", "linux"], description="Supported platforms.")
    actions: list[ActionType] = Field(default_factory=lambda: [ActionType.ANALYZE], description="List of actions to perform.")
    feed_name: str | None = Field(default=None, description="Optional target feed name.")


# --- Response Models ---


class PypiDetails(BaseModel):
    name: str
    version: str
    summary: str | None = None
    project_url: str
    release_url: str


class FeedRef(BaseModel):
    name: str
    feed_name: str
    version: str | None = None
    version_url: str | None = None


class InspectResponse(BaseModel):
    name: str
    pypi: PypiDetails | None = None
    pypi_error: str | None = None
    feed: FeedRef | None = None
    feed_error: str | None = None


class DownloadedFile(BaseModel):
    filename: str
    path: str
    size: int


class DownloadResponse(BaseModel):
    name: str
    version: str
    platform: Platform
    python_tag: str
    dest_dir: str
    files: list[DownloadedFile]


class FeedInfoResponse(BaseModel):
    name: str
    feed_name: str
    current_version: str | None = None
    current_version_url: str | None = None
    available_versions: list[str] = Field(default_factory=list)
    target_version: str | None = None
    wheels: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    feed_name: str
    uploaded: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    skip_existing: bool
    output: str


class CompatRow(BaseModel):
    package: str
    version: str | None = None
    pure_py3_none_any: bool = Field(description="True if a pure Python universal wheel is available.")
    has_windows: bool = Field(description="True if a compatible Windows wheel is available.")
    has_linux: bool = Field(description="True if a compatible Linux wheel is available.")
    has_macos: bool = Field(description="True if a compatible macOS wheel is available.")
    feed_upload_needed_windows: bool
    feed_upload_needed_linux: bool
    feed_upload_needed_macos: bool
    classification: str
    notes: str


class CompatCheckResponse(BaseModel):
    feed_name: str
    total: int
    needs_upload: int
    csv_path: str | None = None
    rows: list[CompatRow]


class UploadFromReportResponse(BaseModel):
    feed_name: str
    dry_run: bool
    planned: list[str] = Field(default_factory=list)
    uploaded: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    output: str


class AnalyzeAndFixResponse(BaseModel):
    csv_path: str
    total_processed: int
    analyzed: int
    fixed: int
    errors: int
