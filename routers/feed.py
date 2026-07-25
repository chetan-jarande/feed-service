from fastapi import APIRouter, Depends

from dependencies import _run, get_service
from models import FeedInfoRequest, FeedInfoResponse, UploadRequest, UploadResponse
from services import FeedService

router = APIRouter(prefix="/feed", tags=["Azure DevOps Feed"])


@router.post("/package-info", response_model=FeedInfoResponse)
def feed_package_info(
    req: FeedInfoRequest,
    service: FeedService = Depends(get_service),
) -> FeedInfoResponse:
    return _run(
        lambda: service.feed_package_info(
            name=req.name,
            feed=req.feed_name,
            version=req.version,
        )
    )


@router.post("/upload", response_model=UploadResponse)
def feed_upload(
    req: UploadRequest,
    service: FeedService = Depends(get_service),
) -> UploadResponse:
    return _run(
        lambda: service.upload_wheels(
            whl_paths=req.whl_paths,
            feed=req.feed_name,
            skip_existing=req.skip_existing,
        )
    )
