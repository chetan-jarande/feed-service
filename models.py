from enum import Enum

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """Supported operating system target platforms for wheel resolution."""

    all = "all"
    windows = "windows"
    linux = "linux"
    macos = "macos"


class ActionType(str, Enum):
    """Actions supported in the batch CSV automation pipeline."""

    ANALYZE = "ANALYZE"
    FIX = "FIX"


# --- Request Models ---


class InspectRequest(BaseModel):
    """Request payload for inspecting package details across PyPI and Azure feed."""

    name: str = Field(
        ...,
        min_length=1,
        description="The Python package name to inspect.",
        examples=["requests", "pydantic"],
    )
    feed_name: str | None = Field(
        default=None,
        description="Optional target feed name. Defaults to AZURE_FEED_NAME setting.",
        examples=["MyArtifactFeed"],
    )


class DownloadRequest(BaseModel):
    """Request payload for downloading package wheels from PyPI."""

    name: str = Field(
        ...,
        min_length=1,
        description="The PyPI package name to download.",
        examples=["requests"],
    )
    version: str | None = Field(
        default=None,
        description="The specific version to download. Defaults to the latest version on PyPI.",
        examples=["2.31.0"],
    )
    platform: Platform = Field(
        default=Platform.all,
        description="The target OS platform(s) to download wheels for.",
        examples=[Platform.all, Platform.linux, Platform.windows],
    )
    python_tag: str | None = Field(
        default="cp312",
        description="The Python ABI tag to filter wheels by (e.g. cp312, cp311).",
        examples=["cp312", "cp311", "py3"],
    )
    dest_dir: str | None = Field(
        default=None,
        description="Local directory path to store downloaded wheel files.",
        examples=["./wheels"],
    )


class FeedInfoRequest(BaseModel):
    """Request payload for fetching package version details directly from Azure feed."""

    name: str = Field(
        ...,
        min_length=1,
        description="The package name to query in the private Azure feed.",
        examples=["numpy"],
    )
    feed_name: str | None = Field(
        default=None,
        description="Optional target feed name. Defaults to AZURE_FEED_NAME.",
        examples=["MyArtifactFeed"],
    )
    version: str | None = Field(
        default=None,
        description="Specific version to query. Defaults to the latest available in the feed.",
        examples=["1.26.4"],
    )


class UploadRequest(BaseModel):
    """Request payload for uploading local wheel/package files to Azure feed via Twine."""

    whl_paths: list[str] = Field(
        ...,
        min_length=1,
        description="List of local package file paths (.whl, .tar.gz, .zip) to upload.",
        examples=[["./wheels/requests-2.31.0-py3-none-any.whl"]],
    )
    feed_name: str | None = Field(
        default=None,
        description="Optional target feed name. Defaults to AZURE_FEED_NAME.",
        examples=["MyArtifactFeed"],
    )
    skip_existing: bool = Field(
        default=True,
        description="If true, pre-checks feed index to skip already-published wheel files.",
        examples=[True],
    )


class CompatCheckRequest(BaseModel):
    """Request payload for generating bulk Python/OS compatibility matrix."""

    packages: list[str] = Field(
        default_factory=list,
        description="List of package specifications (e.g., 'requests==2.31.0' or 'pydantic').",
        examples=[["requests==2.31.0", "pydantic>=2.6.0"]],
    )
    requirements_path: str | None = Field(
        default=None,
        description="Optional path to a requirements.txt file on disk.",
        examples=["./requirements.txt"],
    )
    feed_name: str | None = Field(
        default=None,
        description="Optional target feed name. Defaults to AZURE_FEED_NAME.",
        examples=["MyArtifactFeed"],
    )
    dest_csv: str | None = Field(
        default=None,
        description="Optional path to save output report as a CSV file.",
        examples=["./reports/compat_report.csv"],
    )
    include_pypi: bool = Field(
        default=True,
        description="Whether to fall back to PyPI when package/version is missing from feed.",
        examples=[True],
    )
    python_tag: str = Field(
        default="cp312",
        description="The Python ABI tag to evaluate compatibility against.",
        examples=["cp312", "cp311"],
    )
    resolve_dependencies: bool = Field(
        default=False,
        description="If true, recursively fetches and checks transitive dependencies from PyPI.",
        examples=[True, False],
    )


class UploadFromReportRequest(BaseModel):
    """Request payload for automated wheel backfilling driven by a compatibility CSV report."""

    csv_path: str = Field(
        ...,
        min_length=1,
        description="Path to a previously generated compatibility CSV report.",
        examples=["./reports/compat_report.csv"],
    )
    feed_name: str | None = Field(
        default=None,
        description="Optional target feed name. Defaults to AZURE_FEED_NAME.",
        examples=["MyArtifactFeed"],
    )
    dry_run: bool = Field(
        default=True,
        description="If true, previews download and upload actions without making network changes.",
        examples=[True, False],
    )
    dest_dir: str | None = Field(
        default=None,
        description="Local directory to temporarily store downloaded wheels before upload.",
        examples=["./wheels"],
    )
    python_tag: str = Field(
        default="cp312",
        description="The Python ABI tag used for downloading missing wheels.",
        examples=["cp312"],
    )


class AnalyzeAndFixRequest(BaseModel):
    """Request payload for single-endpoint batch CSV analysis and automatic feed backfill."""

    csv_path: str = Field(
        ...,
        min_length=1,
        description="Path to local input CSV containing 'package name' and 'version to upgrade to' columns.",
        examples=["sample_upgrade.csv"],
    )
    python_tag: str = Field(
        default="cp312",
        description="Python version compatibility tag (e.g. cp312, cp311, py312).",
        examples=["cp312", "cp311"],
    )
    platforms: list[str] = Field(
        default_factory=lambda: ["windows", "linux"],
        description="Target operating system platforms to check and backfill.",
        examples=[["windows", "linux"], ["windows", "linux", "macos"]],
    )
    actions: list[ActionType] = Field(
        default_factory=lambda: [ActionType.ANALYZE],
        description="Pipeline actions to perform: 'ANALYZE' inspects, 'FIX' downloads and uploads missing wheels.",
        examples=[[ActionType.ANALYZE], [ActionType.ANALYZE, ActionType.FIX]],
    )
    feed_name: str | None = Field(
        default=None,
        description="Optional target Azure feed name. Defaults to AZURE_FEED_NAME setting.",
        examples=["MyArtifactFeed"],
    )


# --- Response Models ---


class PypiDetails(BaseModel):
    """Response sub-schema detailing PyPI package release information."""

    name: str = Field(description="Package name as registered on PyPI.", examples=["requests"])
    version: str = Field(description="Latest or target version on PyPI.", examples=["2.31.0"])
    summary: str | None = Field(
        default=None,
        description="Package summary description.",
        examples=["Python HTTP for Humans."],
    )
    project_url: str = Field(
        description="Public PyPI project page URL.",
        examples=["https://pypi.org/project/requests"],
    )
    release_url: str = Field(
        description="Specific release URL on PyPI.",
        examples=["https://pypi.org/project/requests/2.31.0"],
    )


class FeedRef(BaseModel):
    """Response sub-schema detailing Azure DevOps feed package reference."""

    name: str = Field(description="Package name in the Azure feed.", examples=["requests"])
    feed_name: str = Field(description="Azure Artifacts feed name.", examples=["MyArtifactFeed"])
    version: str | None = Field(
        default=None,
        description="Current package version present in the feed.",
        examples=["2.28.0"],
    )
    version_url: str | None = Field(
        default=None,
        description="Azure DevOps UI direct URL to the package version.",
        examples=["https://myorg.visualstudio.com/MyProject/_artifacts/feed/MyArtifactFeed/PyPI/requests/2.28.0"],
    )


class InspectResponse(BaseModel):
    """Response payload for package inspection across PyPI and Azure feed."""

    name: str = Field(description="Requested package name.", examples=["requests"])
    pypi: PypiDetails | None = Field(default=None, description="PyPI release details if found.")
    pypi_error: str | None = Field(default=None, description="Error message if PyPI lookup failed.")
    feed: FeedRef | None = Field(default=None, description="Azure feed details if found.")
    feed_error: str | None = Field(default=None, description="Error message if Azure feed lookup failed.")


class DownloadedFile(BaseModel):
    """Response sub-schema detailing a downloaded wheel or distribution file."""

    filename: str = Field(description="Downloaded file name.", examples=["requests-2.31.0-py3-none-any.whl"])
    path: str = Field(
        description="Absolute local file path.", examples=["/tmp/wheels/requests-2.31.0-py3-none-any.whl"]
    )
    size: int = Field(description="File size in bytes.", examples=[67412])


class DownloadResponse(BaseModel):
    """Response payload for wheel download operations."""

    name: str = Field(description="Package name downloaded.", examples=["requests"])
    version: str = Field(description="Downloaded package version.", examples=["2.31.0"])
    platform: Platform = Field(description="Target platform filter requested.", examples=[Platform.all])
    python_tag: str = Field(description="Python ABI tag used.", examples=["cp312"])
    dest_dir: str = Field(description="Local directory where files were stored.", examples=["./wheels"])
    files: list[DownloadedFile] = Field(
        default_factory=list,
        description="List of successfully downloaded files.",
    )


class FeedInfoResponse(BaseModel):
    """Response payload for feed package information queries."""

    name: str = Field(description="Package name in feed.", examples=["pydantic"])
    feed_name: str = Field(description="Feed name queried.", examples=["MyArtifactFeed"])
    current_version: str | None = Field(default=None, description="Latest version found in feed.", examples=["2.6.0"])
    current_version_url: str | None = Field(default=None, description="Azure UI URL for latest version.")
    available_versions: list[str] = Field(
        default_factory=list,
        description="List of all versions present in the feed.",
        examples=[["1.10.0", "2.5.0", "2.6.0"]],
    )
    target_version: str | None = Field(default=None, description="Requested target version.", examples=["2.6.0"])
    wheels: list[str] = Field(
        default_factory=list,
        description="List of wheel filenames associated with target version.",
        examples=[["pydantic-2.6.0-py3-none-any.whl"]],
    )


class UploadResponse(BaseModel):
    """Response payload for wheel upload operations."""

    feed_name: str = Field(description="Target Azure feed name.", examples=["MyArtifactFeed"])
    uploaded: list[str] = Field(
        default_factory=list,
        description="List of wheel filenames successfully uploaded.",
        examples=[["requests-2.31.0-py3-none-any.whl"]],
    )
    skipped: list[str] = Field(
        default_factory=list,
        description="List of wheel filenames skipped (already in feed).",
        examples=[[]],
    )
    skip_existing: bool = Field(description="Whether skip_existing pre-check was enabled.", examples=[True])
    output: str = Field(
        description="Redacted execution log output from Twine upload.", examples=["Uploading requests-2.31.0... 100%"]
    )


class CompatRow(BaseModel):
    """Detailed row structure in a compatibility assessment report."""

    package: str = Field(description="Package name.", examples=["requests"])
    version: str | None = Field(default=None, description="Evaluated version.", examples=["2.31.0"])
    pure_py3_none_any: bool = Field(description="True if a pure Python universal wheel is available.", examples=[True])
    has_windows: bool = Field(description="True if a compatible Windows wheel is available.", examples=[True])
    has_linux: bool = Field(description="True if a compatible Linux wheel is available.", examples=[True])
    has_macos: bool = Field(description="True if a compatible macOS wheel is available.", examples=[True])
    feed_upload_needed_windows: bool = Field(
        description="True if Windows wheel needs to be backfilled into feed.", examples=[False]
    )
    feed_upload_needed_linux: bool = Field(
        description="True if Linux wheel needs to be backfilled into feed.", examples=[False]
    )
    feed_upload_needed_macos: bool = Field(
        description="True if macOS wheel needs to be backfilled into feed.", examples=[False]
    )
    classification: str = Field(
        description="Compatibility status: OK, NEEDS FEED UPLOAD, SDIST ONLY, or NEEDS WHEEL REBUILD.",
        examples=["OK"],
    )
    notes: str = Field(description="Human-readable assessment commentary.", examples=["Fully compatible in feed"])


class CompatCheckResponse(BaseModel):
    """Response payload for bulk compatibility assessment."""

    feed_name: str = Field(description="Target feed evaluated.", examples=["MyArtifactFeed"])
    total: int = Field(description="Total count of packages evaluated.", examples=[12])
    needs_upload: int = Field(description="Count of packages needing feed backfill.", examples=[2])
    csv_path: str | None = Field(
        default=None, description="Path to generated CSV report if requested.", examples=["./compat.csv"]
    )
    rows: list[CompatRow] = Field(default_factory=list, description="List of per-package compatibility results.")


class UploadFromReportResponse(BaseModel):
    """Response payload for automated feed backfills driven by CSV report."""

    feed_name: str = Field(description="Target Azure feed name.", examples=["MyArtifactFeed"])
    dry_run: bool = Field(description="Whether dry-run mode was active.", examples=[True])
    planned: list[str] = Field(
        default_factory=list,
        description="List of package specifications planned for backfill.",
        examples=[["numpy==1.26.4"]],
    )
    uploaded: list[str] = Field(default_factory=list, description="List of wheel filenames uploaded.")
    skipped: list[str] = Field(default_factory=list, description="List of wheel filenames skipped.")
    unavailable: list[str] = Field(
        default_factory=list, description="List of packages whose wheels could not be retrieved."
    )
    output: str = Field(description="Execution summary log.", examples=["Dry run completed."])


class AnalyzeAndFixResponse(BaseModel):
    """Response payload for batch CSV analyze and fix operations."""

    csv_path: str = Field(description="Path to processed CSV file.", examples=["sample_upgrade.csv"])
    total_processed: int = Field(description="Total number of package rows processed.", examples=[10])
    analyzed: int = Field(description="Count of package rows analyzed.", examples=[10])
    fixed: int = Field(description="Count of package rows successfully fixed/uploaded.", examples=[2])
    errors: int = Field(description="Count of rows that encountered errors.", examples=[0])
