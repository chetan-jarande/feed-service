from fastapi.testclient import TestClient

import main
from config import get_settings
from models import Platform
from services import FeedService

client = TestClient(main.app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Python Feed Service"}


def test_inspect_validation_error() -> None:
    response = client.post("/packages/inspect", json={"name": ""})
    assert response.status_code == 422


def test_upload_missing_file_is_bad_request(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_PAT", "dummy_pat_12345")
    get_settings.cache_clear()

    response = client.post(
        "/feed/upload",
        json={"whl_paths": ["/non/existent/path/package-1.0.0-cp312-cp312-manylinux_x86_64.whl"]},
    )
    assert response.status_code == 400
    assert "File not found" in response.json()["detail"]


def test_upload_requires_at_least_one_path() -> None:
    response = client.post("/feed/upload", json={"whl_paths": []})
    assert response.status_code == 422


def test_select_wheels_both_platforms() -> None:
    files = [
        {"filename": "pkg-1.0.0-py3-none-any.whl", "packagetype": "bdist_wheel"},
        {"filename": "pkg-1.0.0-cp312-cp312-win_amd64.whl", "packagetype": "bdist_wheel"},
        {
            "filename": "pkg-1.0.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
            "packagetype": "bdist_wheel",
        },
        {"filename": "pkg-1.0.0-cp312-cp312-manylinux_2_17_aarch64.whl", "packagetype": "bdist_wheel"},
        {"filename": "pkg-1.0.0.tar.gz", "packagetype": "sdist"},
    ]

    selected = FeedService._select_wheels(files, platform=Platform.all, python_tag="cp312")
    filenames = [f["filename"] for f in selected]

    assert "pkg-1.0.0-py3-none-any.whl" in filenames
    assert "pkg-1.0.0-cp312-cp312-win_amd64.whl" in filenames
    assert "pkg-1.0.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl" in filenames
    assert "pkg-1.0.0-cp312-cp312-manylinux_2_17_aarch64.whl" not in filenames
    assert "pkg-1.0.0.tar.gz" not in filenames


def test_select_wheels_linux_excludes_windows() -> None:
    files = [
        {"filename": "pkg-1.0.0-py3-none-any.whl", "packagetype": "bdist_wheel"},
        {"filename": "pkg-1.0.0-cp312-cp312-win_amd64.whl", "packagetype": "bdist_wheel"},
        {"filename": "pkg-1.0.0-cp312-cp312-manylinux_2_17_x86_64.whl", "packagetype": "bdist_wheel"},
    ]

    selected = FeedService._select_wheels(files, platform=Platform.linux, python_tag="cp312")
    filenames = [f["filename"] for f in selected]

    assert "pkg-1.0.0-py3-none-any.whl" in filenames
    assert "pkg-1.0.0-cp312-cp312-manylinux_2_17_x86_64.whl" in filenames
    assert "pkg-1.0.0-cp312-cp312-win_amd64.whl" not in filenames


def test_select_wheels_python_tag_filter() -> None:
    files = [
        {"filename": "pkg-1.0.0-py3-none-any.whl", "packagetype": "bdist_wheel"},
        {"filename": "pkg-1.0.0-cp311-cp311-win_amd64.whl", "packagetype": "bdist_wheel"},
        {"filename": "pkg-1.0.0-cp312-cp312-win_amd64.whl", "packagetype": "bdist_wheel"},
        {"filename": "pkg-1.0.0-cp312-abi3-win_amd64.whl", "packagetype": "bdist_wheel"},
    ]

    selected = FeedService._select_wheels(files, platform=Platform.windows, python_tag="cp312")
    filenames = [f["filename"] for f in selected]

    assert "pkg-1.0.0-py3-none-any.whl" in filenames
    assert "pkg-1.0.0-cp312-cp312-win_amd64.whl" in filenames
    assert "pkg-1.0.0-cp312-abi3-win_amd64.whl" in filenames
    assert "pkg-1.0.0-cp311-cp311-win_amd64.whl" not in filenames


def test_azure_devops_ui_base_dynamic_construction(monkeypatch) -> None:
    from config import Settings

    monkeypatch.setenv("AZURE_ORG", "myorg")
    monkeypatch.setenv("AZURE_PROJECT_NAME", "Sample Project")
    monkeypatch.delenv("AZURE_DEVOPS_UI_BASE", raising=False)

    s = Settings()
    assert s.azure_devops_ui_base == "https://myorg.visualstudio.com/Sample%20Project"


def test_analyze_and_fix_endpoint_validation_error() -> None:
    response = client.post(
        "/packages/analyze-and-fix",
        json={"csv_path": ""},
    )
    assert response.status_code == 422


def test_analyze_and_fix_endpoint_missing_file() -> None:
    response = client.post(
        "/packages/analyze-and-fix",
        json={
            "csv_path": "non_existent_file.csv",
            "actions": ["ANALYZE"],
        },
    )
    assert response.status_code == 400
    assert "CSV file not found" in response.json()["detail"]


def test_analyze_and_fix_flow(tmp_path) -> None:
    csv_file = tmp_path / "test_upgrade.csv"
    csv_file.write_text(
        "package name,current version,version to upgrade to\nrequests,2.28.0,latest\ninvalid-pkg,,1.0.0\n",
        encoding="utf-8",
    )

    response = client.post(
        "/packages/analyze-and-fix",
        json={
            "csv_path": str(csv_file),
            "python_tag": "cp312",
            "platforms": ["windows", "linux"],
            "actions": ["ANALYZE"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_processed"] == 2

    # Read the updated CSV and verify columns
    import csv

    with open(csv_file, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert "pypi_index" in rows[0]
    assert "feed_details" in rows[0]
    assert "result" in rows[0]
    assert rows[0]["result"] == "PASS: Analyzed"
    # invalid-pkg is not on PyPI during testing or is an upstream error
    assert "PASS" in rows[1]["result"] or "FAILED" in rows[1]["result"]


def test_lifespan_http_session() -> None:
    from fastapi.testclient import TestClient

    from dependencies import create_http_session
    from main import app

    session = create_http_session(pool_maxsize=10, retries=2)
    assert session is not None
    session.close()

    with TestClient(app) as test_client:
        response = test_client.get("/health")
        assert response.status_code == 200
        assert hasattr(app.state, "http_session")
        assert app.state.http_session is not None


def test_analyze_and_fix_empty_csv(tmp_path) -> None:
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("package name,current version,version to upgrade to\n", encoding="utf-8")

    response = client.post(
        "/packages/analyze-and-fix",
        json={
            "csv_path": str(csv_file),
            "actions": ["ANALYZE"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_processed"] == 0


def test_compat_check_endpoint() -> None:
    response = client.post(
        "/packages/compat-check",
        json={
            "packages": ["requests==2.31.0"],
            "python_tag": "cp312",
            "include_pypi": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["rows"]) == 1
    assert data["rows"][0]["package"] == "requests"


def test_download_endpoint() -> None:
    response = client.post(
        "/packages/download",
        json={
            "name": "nonexistentpackage1234567890qwerty",
            "python_tag": "cp312",
        },
    )
    assert response.status_code == 404
