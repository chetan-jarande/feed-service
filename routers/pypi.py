from fastapi import APIRouter, Depends

from dependencies import _run, get_service
from models import DownloadRequest, DownloadResponse
from services import FeedService

router = APIRouter(prefix="/packages", tags=["PyPI"])


@router.post(
    "/download",
    response_model=DownloadResponse,
    description="Download compatible wheel files from PyPI based on Python ABI tag and OS target platform.",
)
def download_package(
    req: DownloadRequest,
    service: FeedService = Depends(get_service),
) -> DownloadResponse:
    """Downloads PyPI wheels matching requested Python tag and platform specifications."""
    return _run(
        lambda: service.download_wheels(
            name=req.name,
            version=req.version,
            platform=req.platform,
            python_tag=req.python_tag,
            dest_dir=req.dest_dir,
        )
    )
