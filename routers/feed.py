from fastapi import APIRouter, Depends

from dependencies import _run, get_service
from models import FeedInfoRequest, FeedInfoResponse, UploadRequest, UploadResponse
from services import FeedService

router = APIRouter(prefix="/feed", tags=["Azure DevOps Feed"])


@router.post(
    "/package-info",
    response_model=FeedInfoResponse,
    description="Fetch available package versions and wheel files present on target Azure Artifacts feed.",
)
def feed_package_info(
    req: FeedInfoRequest,
    service: FeedService = Depends(get_service),
) -> FeedInfoResponse:
    """Queries package details and available wheels directly from the private feed."""
    return _run(
        lambda: service.feed_package_info(
            name=req.name,
            feed=req.feed_name,
            version=req.version,
        )
    )


@router.post(
    "/upload",
    response_model=UploadResponse,
    description="Upload local wheel and package files to target Azure feed using Twine with PAT redaction.",
)
def feed_upload(
    req: UploadRequest,
    service: FeedService = Depends(get_service),
) -> UploadResponse:
    """Uploads wheel files to target feed, automatically avoiding duplicate conflict errors when skip_existing is enabled."""
    return _run(
        lambda: service.upload_wheels(
            whl_paths=req.whl_paths,
            feed=req.feed_name,
            skip_existing=req.skip_existing,
        )
    )
