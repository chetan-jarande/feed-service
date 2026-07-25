import base64
import csv
import os
import re
import subprocess
import sys
from typing import ClassVar
from urllib.parse import unquote

import packaging.version
import requests

from config import Settings
from logger import get_logger
from models import (
    ActionType,
    AnalyzeAndFixRequest,
    AnalyzeAndFixResponse,
    CompatCheckResponse,
    CompatRow,
    DownloadedFile,
    DownloadResponse,
    FeedInfoResponse,
    FeedRef,
    InspectResponse,
    Platform,
    PypiDetails,
    UploadFromReportResponse,
    UploadResponse,
)


class NotFoundError(Exception):
    pass


class BadRequestError(Exception):
    pass


class UpstreamError(Exception):
    pass


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _vkey(v: str) -> packaging.version.Version:
    try:
        return packaging.version.Version(v)
    except (packaging.version.InvalidVersion, TypeError, ValueError):
        return packaging.version.Version("0")


class FeedService:
    CSV_FIELDS: ClassVar[list[str]] = [
        "package",
        "version",
        "pure_py3_none_any",
        "has_windows",
        "has_linux",
        "has_macos",
        "feed_upload_needed_windows",
        "feed_upload_needed_linux",
        "feed_upload_needed_macos",
        "classification",
        "notes",
    ]

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger(__name__)

    def _auth_header(self) -> dict[str, str]:
        if self.settings.azure_pat:
            encoded = base64.b64encode(f":{self.settings.azure_pat}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    def _get(self, url: str, auth: bool = False) -> requests.Response:
        try:
            headers = self._auth_header() if auth else {}
            resp = requests.get(url, headers=headers, timeout=self.settings.request_timeout)
            return resp
        except Exception as e:
            raise UpstreamError(f"HTTP request to {url} failed: {e}") from e

    def pypi_info(self, name: str) -> dict:
        normalized_name = _norm(name)
        url = f"{self.settings.pypi_json_base}/{normalized_name}/json"
        resp = self._get(url)
        if resp.status_code == 404:
            raise NotFoundError(f"Package '{name}' not found on PyPI")
        if resp.status_code != 200:
            raise UpstreamError(f"PyPI returned status code {resp.status_code} for package '{name}'")
        try:
            return resp.json()
        except Exception as e:
            raise UpstreamError(f"Failed to parse PyPI response for '{name}': {e}") from e

    def pypi_latest(self, name: str) -> PypiDetails:
        data = self.pypi_info(name)
        info = data.get("info", {})
        version = info.get("version", "0.0.0")
        summary = info.get("summary")
        normalized = _norm(name)
        project_url = f"{self.settings.pypi_project_base}/{normalized}"
        release_url = f"{self.settings.pypi_project_base}/{normalized}/{version}"
        return PypiDetails(
            name=info.get("name", name),
            version=version,
            summary=summary,
            project_url=project_url,
            release_url=release_url,
        )

    def _feed_query(self, feed: str, query: str) -> dict:
        url = f"{self.settings.feeds_api_base}/{feed}/packages?packageNameQuery={query}&api-version={self.settings.azure_api_version}"
        resp = self._get(url, auth=True)
        if resp.status_code == 404:
            raise NotFoundError(f"Feed '{feed}' not found")
        if resp.status_code != 200:
            raise UpstreamError(f"Azure feed API returned status code {resp.status_code}")
        try:
            return resp.json()
        except Exception as e:
            raise UpstreamError(f"Failed to parse feed response: {e}") from e

    def find_feed_package(self, name: str, feed: str) -> dict:
        norm_target = _norm(name)
        queries = [
            name,
            norm_target,
            name.replace("-", "."),
            name.replace(".", "-"),
        ]
        # Deduplicate queries keeping order
        seen_queries = set()
        unique_queries = []
        for q in queries:
            if q not in seen_queries:
                seen_queries.add(q)
                unique_queries.append(q)

        for q in unique_queries:
            try:
                res = self._feed_query(feed, q)
                for pkg in res.get("value", []):
                    if _norm(pkg.get("name", "")) == norm_target:
                        return pkg
            except NotFoundError:
                raise
            except UpstreamError as e:
                self.logger.debug(f"Feed query '{q}' failed: {e}")
                continue

        raise NotFoundError(f"Package '{name}' not found in feed '{feed}'")

    def feed_version_files(self, feed: str, pkg_id: str, ver_id: str) -> list[str]:
        url = f"{self.settings.feeds_api_base}/{feed}/packages/{pkg_id}/versions/{ver_id}?api-version={self.settings.azure_api_version}&includeFiles=true"
        resp = self._get(url, auth=True)
        if resp.status_code != 200:
            raise UpstreamError(f"Failed to fetch version files for package {pkg_id} version {ver_id}")
        try:
            data = resp.json()
            return [f["name"] for f in data.get("files", []) if "name" in f]
        except Exception as e:
            raise UpstreamError(f"Failed to parse version files response: {e}") from e

    def feed_overview_url(self, feed: str, name: str, version: str | None = None) -> str:
        base = self.settings.azure_devops_ui_base.rstrip("/")
        ver_part = f"/{version}" if version else ""
        return f"{base}/_artifacts/feed/{feed}/PyPI/{name}{ver_part}"

    def feed_existing_filenames(self, feed: str, package_name: str) -> set[str]:
        url = f"{self.settings.simple_index_url(feed)}/{_norm(package_name)}/"
        resp = self._get(url, auth=True)
        if resp.status_code == 404:
            return set()
        if resp.status_code != 200:
            return set()

        text = resp.text
        # Parse links e.g. <a href="...">filename</a> or href="filename#..."
        raw_filenames = re.findall(r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', text, re.IGNORECASE)
        filenames = set()
        for href, inner in raw_filenames:
            # href or inner text might contain filename
            fn = unquote(href.split("#")[0].split("/")[-1].strip())
            if fn:
                filenames.add(fn)
            fn_inner = unquote(inner.strip())
            if fn_inner:
                filenames.add(fn_inner)

        # Also search for standard file pattern in text
        pattern = re.findall(r"([a-zA-Z0-9_.-]+(?:\.whl|\.tar\.gz|\.zip))", text)
        for p in pattern:
            filenames.add(p)

        return filenames

    def feed_package_info(self, name: str, feed: str | None = None, version: str | None = None) -> FeedInfoResponse:
        target_feed = feed or self.settings.azure_feed_name
        pkg = self.find_feed_package(name, target_feed)
        versions_raw = pkg.get("versions", [])
        if not versions_raw:
            raise NotFoundError(f"Package '{name}' in feed '{target_feed}' has no versions")

        avail_versions = sorted([v["version"] for v in versions_raw], key=_vkey, reverse=True)
        current_version = avail_versions[0]
        target_ver_str = version if version else current_version

        ver_obj = None
        for v in versions_raw:
            if v["version"] == target_ver_str:
                ver_obj = v
                break

        wheels: list[str] = []
        if ver_obj:
            files = self.feed_version_files(target_feed, pkg["id"], ver_obj["id"])
            wheels = [f for f in files if f.endswith(".whl")]

        current_version_url = (
            self.feed_overview_url(target_feed, pkg["name"], current_version) if current_version else None
        )

        return FeedInfoResponse(
            name=pkg.get("name", name),
            feed_name=target_feed,
            current_version=current_version,
            current_version_url=current_version_url,
            available_versions=avail_versions,
            target_version=target_ver_str,
            wheels=wheels,
        )

    def inspect(self, name: str, feed: str | None = None) -> InspectResponse:
        target_feed = feed or self.settings.azure_feed_name
        pypi_details: PypiDetails | None = None
        pypi_err: str | None = None
        feed_ref: FeedRef | None = None
        feed_err: str | None = None

        try:
            pypi_details = self.pypi_latest(name)
        except (NotFoundError, UpstreamError) as e:
            pypi_err = str(e)

        try:
            info = self.feed_package_info(name, feed=target_feed)
            feed_ref = FeedRef(
                name=info.name,
                feed_name=target_feed,
                version=info.current_version,
                version_url=info.current_version_url,
            )
        except (NotFoundError, UpstreamError) as e:
            feed_err = str(e)

        if pypi_details is None and feed_ref is None:
            raise NotFoundError(f"Package '{name}' not found on PyPI or feed '{target_feed}'")

        return InspectResponse(
            name=name,
            pypi=pypi_details,
            pypi_error=pypi_err,
            feed=feed_ref,
            feed_error=feed_err,
        )

    @staticmethod
    def _select_wheels(files: list[dict], platform: Platform | str, python_tag: str | None = "cp312") -> list[dict]:
        selected = []
        plat_str = platform.value if isinstance(platform, Platform) else str(platform).lower()

        # Architecture exclusions (non-x86_64/arm64 macOS)
        excluded_archs = {"aarch64", "arm64", "ppc64le", "s390x", "i686", "win32", "musllinux"}

        for f in files:
            filename = f.get("filename", "")
            packagetype = f.get("packagetype", "")
            if not filename.endswith(".whl") and packagetype != "bdist_wheel":
                continue

            fn_lower = filename.lower()

            # Explicitly allow macOS arm64/universal2 if the platform requests macOS, otherwise exclude arm architectures
            is_macos = "macosx" in fn_lower or "universal2" in fn_lower

            # Normal architecture exclusions for linux/windows if not macOS
            if not is_macos and any(arch in fn_lower for arch in excluded_archs):
                continue
            is_pure = "py3-none-any" in fn_lower or "py2.py3-none-any" in fn_lower

            if is_pure:
                selected.append(f)
                continue

            # Python tag check (must match tag or abi3)
            if python_tag:
                tag_lower = python_tag.lower()
                if tag_lower not in fn_lower and "abi3" not in fn_lower:
                    continue

            # Platform check
            is_win = "win_amd64" in fn_lower
            is_linux = "manylinux" in fn_lower or "linux_x86_64" in fn_lower
            is_macos = "macosx" in fn_lower or "universal2" in fn_lower

            if (
                (plat_str == "all" and (is_win or is_linux or is_macos))
                or (plat_str == "windows" and is_win)
                or (plat_str == "linux" and is_linux)
                or (plat_str == "macos" and is_macos)
            ):
                selected.append(f)

        return selected

    def download_wheels(
        self,
        name: str,
        version: str | None = None,
        platform: Platform | str = Platform.all,
        python_tag: str | None = None,
        dest_dir: str | None = None,
    ) -> DownloadResponse:
        data = self.pypi_info(name)
        target_version = version or data.get("info", {}).get("version")
        if not target_version:
            raise NotFoundError(f"Could not determine version for '{name}'")

        releases = data.get("releases", {})
        files = releases.get(target_version, [])
        if not files:
            raise NotFoundError(f"No release files found for '{name}=={target_version}' on PyPI")

        p_tag = python_tag or self.settings.default_python_tag
        selected_files = self._select_wheels(files, platform=platform, python_tag=p_tag)
        if not selected_files:
            raise NotFoundError(f"No matching wheel files found for '{name}=={target_version}' on PyPI")

        target_dir = dest_dir or self.settings.default_download_dir
        os.makedirs(target_dir, exist_ok=True)

        downloaded: list[DownloadedFile] = []
        for f in selected_files:
            url = f.get("url")
            filename = f.get("filename")
            if not url or not filename:
                continue

            file_path = os.path.join(target_dir, filename)
            resp = requests.get(url, stream=True, timeout=self.settings.request_timeout)
            if resp.status_code != 200:
                raise UpstreamError(f"Failed to download wheel from {url}")

            with open(file_path, "wb") as fh:
                fh.writelines(resp.iter_content(chunk_size=8192))

            size = os.path.getsize(file_path)
            downloaded.append(DownloadedFile(filename=filename, path=os.path.abspath(file_path), size=size))

        plat_enum = Platform(platform) if isinstance(platform, str) else platform

        return DownloadResponse(
            name=name,
            version=target_version,
            platform=plat_enum,
            python_tag=p_tag,
            dest_dir=target_dir,
            files=downloaded,
        )

    def upload_wheels(
        self,
        whl_paths: list[str],
        feed: str | None = None,
        skip_existing: bool = True,
    ) -> UploadResponse:
        target_feed = feed or self.settings.azure_feed_name

        if not self.settings.azure_pat:
            raise BadRequestError("AZURE_PAT is required for uploading to feed")

        if not whl_paths:
            raise BadRequestError("whl_paths cannot be empty")

        valid_exts = (".whl", ".tar.gz", ".zip")
        files_to_check = []
        for p in whl_paths:
            if not os.path.isfile(p):
                raise BadRequestError(f"File not found: {p}")
            if not p.endswith(valid_exts):
                raise BadRequestError(f"Invalid file extension: {p}. Must be one of {valid_exts}")
            files_to_check.append(p)

        skipped_files: list[str] = []
        upload_files: list[str] = []

        if skip_existing:
            for p in files_to_check:
                filename = os.path.basename(p)
                # Parse package name from filename e.g. package-1.0.0-cp312-none-any.whl
                pkg_name = filename.split("-")[0]
                existing = self.feed_existing_filenames(target_feed, pkg_name)
                if filename in existing:
                    skipped_files.append(filename)
                else:
                    upload_files.append(p)
        else:
            upload_files = files_to_check

        if not upload_files:
            return UploadResponse(
                feed_name=target_feed,
                uploaded=[],
                skipped=skipped_files,
                skip_existing=skip_existing,
                output="All files skipped (already exist in feed).",
            )

        upload_url = self.settings.upload_url(target_feed)
        cmd = [
            sys.executable,
            "-m",
            "twine",
            "upload",
            "--repository-url",
            upload_url,
            "--username",
            "__token__",
            "--password",
            self.settings.azure_pat,
            "--non-interactive",
            "--disable-progress-bar",
        ] + upload_files

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.settings.upload_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise UpstreamError("Twine upload timed out") from e
        except FileNotFoundError as e:
            raise UpstreamError("Twine executable not found") from e
        except Exception as e:
            raise UpstreamError(f"Twine upload failed: {e}") from e

        # Redact PAT from output
        out = res.stdout.replace(self.settings.azure_pat, "***") if res.stdout else ""
        err = res.stderr.replace(self.settings.azure_pat, "***") if res.stderr else ""
        combined_output = f"{out}\n{err}".strip()

        if res.returncode != 0:
            raise UpstreamError(f"Twine upload failed with return code {res.returncode}:\n{combined_output}")

        uploaded_names = [os.path.basename(p) for p in upload_files]
        return UploadResponse(
            feed_name=target_feed,
            uploaded=uploaded_names,
            skipped=skipped_files,
            skip_existing=skip_existing,
            output=combined_output,
        )

    @staticmethod
    def _wheel_flags(filenames: list[str], python_tag: str = "cp312") -> dict[str, bool]:
        pure = win = linux = macos = False
        ptag_lower = python_tag.lower()

        for fn in filenames:
            fn_lower = fn.lower()
            if "py3-none-any" in fn_lower or "py2.py3-none-any" in fn_lower:
                pure = win = linux = macos = True
            else:
                has_tag = ptag_lower in fn_lower or "abi3" in fn_lower
                if has_tag:
                    if "win_amd64" in fn_lower:
                        win = True
                    if ("manylinux" in fn_lower or "linux_x86_64" in fn_lower) and "musllinux" not in fn_lower:
                        linux = True
                    if "macosx" in fn_lower or "universal2" in fn_lower:
                        macos = True

        return {
            "pure_py3_none_any": pure,
            "has_windows": win,
            "has_linux": linux,
            "has_macos": macos,
        }

    def _pypi_flags(self, name: str, version: str, python_tag: str = "cp312") -> tuple[dict[str, bool], bool]:
        try:
            data = self.pypi_info(name)
            releases = data.get("releases", {})
            files = releases.get(version, [])
            filenames = [f["filename"] for f in files if "filename" in f]
            has_sdist = any(
                f.get("packagetype") == "sdist" or f.get("filename", "").endswith((".tar.gz", ".zip")) for f in files
            )
            return self._wheel_flags(filenames, python_tag), has_sdist
        except (NotFoundError, UpstreamError):
            return {"pure_py3_none_any": False, "has_windows": False, "has_linux": False, "has_macos": False}, False

    def compat_row(
        self,
        name: str,
        version: str | None = None,
        feed: str | None = None,
        include_pypi: bool = True,
        python_tag: str = "cp312",
    ) -> CompatRow:
        target_feed = feed or self.settings.azure_feed_name
        resolved_version = version

        # Check feed
        feed_wheels: list[str] = []
        try:
            feed_info = self.feed_package_info(name, feed=target_feed, version=version)
            feed_wheels = feed_info.wheels
            if not resolved_version:
                resolved_version = feed_info.target_version or feed_info.current_version
        except (NotFoundError, UpstreamError):
            self.logger.debug(f"Package '{name}' not found or error querying feed '{target_feed}'")

        # If version still not resolved, check PyPI
        if not resolved_version and include_pypi:
            try:
                pypi_det = self.pypi_latest(name)
                resolved_version = pypi_det.version
            except (NotFoundError, UpstreamError):
                self.logger.debug(f"Package '{name}' not found on PyPI")

        feed_flags = self._wheel_flags(feed_wheels, python_tag)

        pypi_flags = {"pure_py3_none_any": False, "has_windows": False, "has_linux": False, "has_macos": False}
        has_sdist = False

        if include_pypi and resolved_version:
            pypi_flags, has_sdist = self._pypi_flags(name, resolved_version, python_tag)

        # Compare feed vs PyPI flags
        pure = feed_flags["pure_py3_none_any"] or pypi_flags["pure_py3_none_any"]
        win_feed = feed_flags["has_windows"]
        linux_feed = feed_flags["has_linux"]
        macos_feed = feed_flags["has_macos"]

        win_pypi = pypi_flags["has_windows"]
        linux_pypi = pypi_flags["has_linux"]
        macos_pypi = pypi_flags["has_macos"]

        needed_win = not win_feed and win_pypi
        needed_linux = not linux_feed and linux_pypi
        needed_macos = not macos_feed and macos_pypi

        if win_feed and linux_feed and macos_feed:
            classification = "OK"
            notes = "Fully compatible in feed"
        elif needed_win or needed_linux or needed_macos:
            classification = "NEEDS FEED UPLOAD"
            notes = "Compatible wheels on PyPI, can be backfilled"
        elif has_sdist and not (win_pypi or linux_pypi or macos_pypi):
            classification = "SDIST ONLY"
            notes = "Only source distribution available on PyPI"
        else:
            classification = "NEEDS WHEEL REBUILD"
            notes = f"No compatible {python_tag} wheels on PyPI or feed"

        return CompatRow(
            package=name,
            version=resolved_version,
            pure_py3_none_any=pure,
            has_windows=win_feed or win_pypi,
            has_linux=linux_feed or linux_pypi,
            has_macos=macos_feed or macos_pypi,
            feed_upload_needed_windows=needed_win,
            feed_upload_needed_linux=needed_linux,
            feed_upload_needed_macos=needed_macos,
            classification=classification,
            notes=notes,
        )

    @staticmethod
    def _parse_specs(
        packages: list[str] | None = None,
        requirements_path: str | None = None,
    ) -> list[tuple[str, str | None]]:
        raw_lines = list(packages or [])

        if requirements_path and os.path.isfile(requirements_path):
            with open(requirements_path, "r", encoding="utf-8") as fh:
                raw_lines.extend(fh.readlines())

        specs: list[tuple[str, str | None]] = []
        seen = set()

        for line in raw_lines:
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            # Strip inline comment
            if "#" in line:
                line = line.split("#")[0].strip()

            if not line:
                continue

            # Parse spec
            match = re.match(r"^([a-zA-Z0-9_.-]+)(?:==|>=|<=|~=|>|<)?([a-zA-Z0-9_.-]+)?", line)
            if match:
                pkg_name = match.group(1)
                ver = match.group(2) if "==" in line else None
                key = (_norm(pkg_name), ver)
                if key not in seen:
                    seen.add(key)
                    specs.append((pkg_name, ver))

        return specs

    def _resolve_transitive_deps(self, initial_specs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
        queue = list(initial_specs)
        seen = {_norm(pkg) for pkg, _ in queue}
        resolved_specs = list(initial_specs)

        while queue:
            pkg, ver = queue.pop(0)
            try:
                url = f"{self.settings.pypi_json_base}/{_norm(pkg)}/{ver}/json" if ver else f"{self.settings.pypi_json_base}/{_norm(pkg)}/json"
                resp = self._get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    reqs = data.get("info", {}).get("requires_dist") or []
                    for req_str in reqs:
                        try:
                            # Basic extraction ignoring extra requirements
                            if "extra ==" in req_str or "extra==" in req_str:
                                continue
                            match = re.match(r"^([a-zA-Z0-9_.-]+)", req_str.strip())
                            if match:
                                dep_pkg = match.group(1)
                                norm_dep = _norm(dep_pkg)
                                if norm_dep not in seen:
                                    seen.add(norm_dep)
                                    queue.append((dep_pkg, None))
                                    resolved_specs.append((dep_pkg, None))
                        except (ValueError, TypeError, KeyError, AttributeError):
                            continue
            except requests.RequestException as e:
                self.logger.debug(f"Failed to resolve dependencies for {pkg}: {e}")

        return resolved_specs

    def compat_check(
        self,
        packages: list[str] | None = None,
        requirements_path: str | None = None,
        feed: str | None = None,
        dest_csv: str | None = None,
        include_pypi: bool = True,
        python_tag: str = "cp312",
        resolve_dependencies: bool = False,
    ) -> CompatCheckResponse:
        target_feed = feed or self.settings.azure_feed_name
        specs = self._parse_specs(packages or [], requirements_path)

        if resolve_dependencies:
            specs = self._resolve_transitive_deps(specs)

        rows: list[CompatRow] = []
        needs_upload_count = 0

        for pkg, ver in specs:
            row = self.compat_row(pkg, version=ver, feed=target_feed, include_pypi=include_pypi, python_tag=python_tag)
            rows.append(row)
            if row.classification == "NEEDS FEED UPLOAD":
                needs_upload_count += 1

        if dest_csv:
            csv_dir = os.path.dirname(dest_csv)
            if csv_dir:
                os.makedirs(csv_dir, exist_ok=True)
            with open(dest_csv, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(self.CSV_FIELDS)
                for r in rows:
                    writer.writerow(
                        [
                            r.package,
                            r.version or "",
                            r.pure_py3_none_any,
                            r.has_windows,
                            r.has_linux,
                            r.has_macos,
                            r.feed_upload_needed_windows,
                            r.feed_upload_needed_linux,
                            r.feed_upload_needed_macos,
                            r.classification,
                            r.notes,
                        ]
                    )

        return CompatCheckResponse(
            feed_name=target_feed,
            total=len(rows),
            needs_upload=needs_upload_count,
            csv_path=dest_csv,
            rows=rows,
        )

    def upload_from_report(
        self,
        csv_path: str,
        feed: str | None = None,
        dry_run: bool = True,
        dest_dir: str | None = None,
    ) -> UploadFromReportResponse:
        target_feed = feed or self.settings.azure_feed_name

        if not os.path.isfile(csv_path):
            raise BadRequestError(f"CSV file not found: {csv_path}")

        planned_rows = []
        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                cls = row.get("classification", "")
                win_needed = row.get("feed_upload_needed_windows", "").lower() in ("true", "1")
                linux_needed = row.get("feed_upload_needed_linux", "").lower() in ("true", "1")
                macos_needed = row.get("feed_upload_needed_macos", "").lower() in ("true", "1")
                if cls == "NEEDS FEED UPLOAD" or win_needed or linux_needed or macos_needed:
                    planned_rows.append(row)

        planned_specs = [
            f"{r.get('package')}=={r.get('version')}" if r.get("version") else r.get("package", "")
            for r in planned_rows
        ]

        if dry_run:
            return UploadFromReportResponse(
                feed_name=target_feed,
                dry_run=True,
                planned=planned_specs,
                uploaded=[],
                skipped=[],
                unavailable=[],
                output="Dry run completed. No files downloaded or uploaded.",
            )

        downloaded_paths: list[str] = []
        unavailable: list[str] = []

        for r in planned_rows:
            pkg = r.get("package")
            ver = r.get("version")
            if not pkg:
                continue

            win_needed = r.get("feed_upload_needed_windows", "").lower() in ("true", "1")
            linux_needed = r.get("feed_upload_needed_linux", "").lower() in ("true", "1")
            macos_needed = r.get("feed_upload_needed_macos", "").lower() in ("true", "1")

            if win_needed and linux_needed and macos_needed:
                plat = Platform.all
            elif win_needed:
                plat = Platform.windows
            elif linux_needed:
                plat = Platform.linux
            elif macos_needed:
                plat = Platform.macos
            else:
                plat = Platform.all

            try:
                dl_res = self.download_wheels(
                    name=pkg,
                    version=ver if ver else None,
                    platform=plat,
                    python_tag=r.get("python_tag", self.settings.default_python_tag),
                    dest_dir=dest_dir,
                )
                for f in dl_res.files:
                    downloaded_paths.append(f.path)
            except (NotFoundError, UpstreamError, requests.RequestException) as e:
                self.logger.warning(f"Failed to download wheels for {pkg}: {e}")
                unavailable.append(f"{pkg}=={ver}" if ver else pkg)

        uploaded: list[str] = []
        skipped: list[str] = []
        output = "No files to upload."

        if downloaded_paths:
            up_res = self.upload_wheels(downloaded_paths, feed=target_feed, skip_existing=True)
            uploaded = up_res.uploaded
            skipped = up_res.skipped
            output = up_res.output

        return UploadFromReportResponse(
            feed_name=target_feed,
            dry_run=False,
            planned=planned_specs,
            uploaded=uploaded,
            skipped=skipped,
            unavailable=unavailable,
            output=output,
        )

    def _analyze_platform_availability(self, files: list[dict], python_tag: str, platforms: list[str]) -> dict:
        result = {python_tag: False}
        for plat in platforms:
            result[plat] = None
            try:
                plat_enum = Platform(plat.lower())
            except ValueError:
                continue

            selected = self._select_wheels(files, platform=plat_enum, python_tag=python_tag)
            if selected:
                result[python_tag] = True
                result[plat] = selected[0].get("filename")
        return result

    def _analyze_action(
        self,
        package: str,
        target_version: str,
        python_tag: str,
        platforms: list[str],
        feed: str
    ) -> tuple[dict, dict, str]:
        resolved_version = target_version
        if target_version.lower() == "latest":
            try:
                pypi_latest = self.pypi_latest(package)
                resolved_version = pypi_latest.version
            except (NotFoundError, UpstreamError):
                pass

        pypi_index = {python_tag: False}
        for p in platforms:
            pypi_index[p] = None

        try:
            data = self.pypi_info(package)
            releases = data.get("releases", {})
            files = releases.get(resolved_version, [])
            pypi_index = self._analyze_platform_availability(files, python_tag, platforms)
        except (NotFoundError, UpstreamError):
            pass

        feed_details = {python_tag: False}
        for p in platforms:
            feed_details[p] = None

        try:
            feed_info = self.feed_package_info(package, feed=feed, version=resolved_version)
            feed_files = [{"filename": fn, "packagetype": "bdist_wheel" if fn.endswith(".whl") else "sdist"} for fn in feed_info.wheels]
            feed_details = self._analyze_platform_availability(feed_files, python_tag, platforms)
        except (NotFoundError, UpstreamError):
            pass

        return pypi_index, feed_details, resolved_version

    def _fix_action(
        self,
        package: str,
        resolved_version: str,
        pypi_index: dict,
        feed_details: dict,
        platforms: list[str],
        feed: str,
        python_tag: str
    ) -> str:
        if not pypi_index.get(python_tag):
            return "FAILED: No compatible wheels on PyPI"

        missing_platforms = []
        for plat in platforms:
            if pypi_index.get(plat) and not feed_details.get(plat):
                missing_platforms.append(plat)

        if not missing_platforms:
            return "PASS: Feed already has all required wheels"

        dest_dir = self.settings.default_download_dir
        os.makedirs(dest_dir, exist_ok=True)
        downloaded_paths = []

        try:
            filenames_to_dl = set()
            for plat in missing_platforms:
                fn = pypi_index.get(plat)
                if fn:
                    filenames_to_dl.add(fn)

            data = self.pypi_info(package)
            releases = data.get("releases", {})
            files = releases.get(resolved_version, [])

            for fn in filenames_to_dl:
                file_info = next((f for f in files if f.get("filename") == fn), None)
                if not file_info:
                    return f"FAILED: Could not find URL for {fn} on PyPI"

                url = file_info.get("url")
                file_path = os.path.join(dest_dir, fn)
                resp = requests.get(url, stream=True, timeout=self.settings.request_timeout)
                if resp.status_code != 200:
                    return f"FAILED: Download failed for {fn}"
                with open(file_path, "wb") as fh:
                    fh.writelines(resp.iter_content(chunk_size=8192))
                downloaded_paths.append(file_path)

            if downloaded_paths:
                self.upload_wheels(downloaded_paths, feed=feed, skip_existing=True)
                return "PASS: Successfully fixed and uploaded missing wheels"

        except (UpstreamError, BadRequestError, requests.RequestException, OSError) as e:
            return f"FAILED: Error during fix: {e}"

        return "PASS: No action needed"

    def process_analyze_and_fix(self, req: AnalyzeAndFixRequest) -> AnalyzeAndFixResponse:
        import json

        if not os.path.isfile(req.csv_path):
            raise BadRequestError(f"CSV file not found: {req.csv_path}")

        target_feed = req.feed_name or self.settings.azure_feed_name

        rows = []
        with open(req.csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames or []
            rows = list(reader)

        for col in ["pypi_index", "feed_details", "result"]:
            if col not in fieldnames:
                fieldnames.append(col)

        analyzed_count = 0
        fixed_count = 0
        errors_count = 0

        for row in rows:
            pkg = row.get("package name", "").strip()
            target_version = row.get("version to upgrade to", "").strip()

            if not pkg or not target_version:
                row["result"] = "FAILED: Missing 'package name' or 'version to upgrade to'"
                errors_count += 1
                continue

            try:
                pypi_idx = {}
                feed_det = {}
                resolved_version = target_version

                if ActionType.ANALYZE in req.actions:
                    pypi_idx, feed_det, resolved_version = self._analyze_action(
                        pkg, target_version, req.python_tag, req.platforms, target_feed
                    )
                    row["pypi_index"] = json.dumps(pypi_idx)
                    row["feed_details"] = json.dumps(feed_det)
                    row["result"] = "PASS: Analyzed"
                    analyzed_count += 1
                else:
                    if row.get("pypi_index"):
                        pypi_idx = json.loads(row["pypi_index"])
                    if row.get("feed_details"):
                        feed_det = json.loads(row["feed_details"])

                if ActionType.FIX in req.actions:
                    if not pypi_idx:
                        pypi_idx, feed_det, resolved_version = self._analyze_action(
                            pkg, target_version, req.python_tag, req.platforms, target_feed
                        )
                        row["pypi_index"] = json.dumps(pypi_idx)
                        row["feed_details"] = json.dumps(feed_det)

                    res = self._fix_action(
                        pkg, resolved_version, pypi_idx, feed_det, req.platforms, target_feed, req.python_tag
                    )
                    row["result"] = res
                    if res.startswith("PASS"):
                        fixed_count += 1
                    else:
                        errors_count += 1

            except (UpstreamError, NotFoundError, BadRequestError, ValueError, KeyError) as e:
                row["result"] = f"FAILED: {e}"
                errors_count += 1

        with open(req.csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return AnalyzeAndFixResponse(
            csv_path=req.csv_path,
            total_processed=len(rows),
            analyzed=analyzed_count,
            fixed=fixed_count,
            errors=errors_count,
        )
