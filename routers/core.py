from fastapi import APIRouter, Depends

from dependencies import _run, get_service
from models import (
    AnalyzeAndFixRequest,
    AnalyzeAndFixResponse,
    CompatCheckRequest,
    CompatCheckResponse,
    InspectRequest,
    InspectResponse,
    UploadFromReportRequest,
    UploadFromReportResponse,
)
from services import FeedService

router = APIRouter(tags=["Core Feed Operations"])


@router.post("/packages/inspect", response_model=InspectResponse)
def inspect_package(
    req: InspectRequest,
    service: FeedService = Depends(get_service),
) -> InspectResponse:
    return _run(lambda: service.inspect(req.name, feed=req.feed_name))


@router.post("/packages/compat-check", response_model=CompatCheckResponse)
def compat_check(
    req: CompatCheckRequest,
    service: FeedService = Depends(get_service),
) -> CompatCheckResponse:
    return _run(
        lambda: service.compat_check(
            packages=req.packages,
            requirements_path=req.requirements_path,
            feed=req.feed_name,
            dest_csv=req.dest_csv,
            include_pypi=req.include_pypi,
            python_tag=req.python_tag,
            resolve_dependencies=req.resolve_dependencies,
        )
    )


@router.post("/feed/upload-from-report", response_model=UploadFromReportResponse)
def upload_from_report(
    req: UploadFromReportRequest,
    service: FeedService = Depends(get_service),
) -> UploadFromReportResponse:
    return _run(
        lambda: service.upload_from_report(
            csv_path=req.csv_path,
            feed=req.feed_name,
            dry_run=req.dry_run,
            dest_dir=req.dest_dir,
        )
    )


@router.post("/packages/analyze-and-fix", response_model=AnalyzeAndFixResponse)
def analyze_and_fix(
    req: AnalyzeAndFixRequest,
    service: FeedService = Depends(get_service),
) -> AnalyzeAndFixResponse:
    return _run(lambda: service.process_analyze_and_fix(req))
