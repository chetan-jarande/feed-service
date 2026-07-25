from collections.abc import Callable
from typing import TypeVar

from fastapi import Depends, HTTPException, status

from config import Settings, get_settings
from services import BadRequestError, FeedService, NotFoundError, UpstreamError


def get_service(settings: Settings = Depends(get_settings)) -> FeedService:
    return FeedService(settings)


T = TypeVar("T")

def _run(fn: Callable[[], T]) -> T:
    try:
        return fn()
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except UpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
