from collections.abc import Callable

import requests
from fastapi import Depends, HTTPException, Request, status
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from config import Settings, get_settings
from services import BadRequestError, FeedService, NotFoundError, UpstreamError


def create_http_session(pool_maxsize: int = 25, retries: int = 3) -> requests.Session:
    """Creates a connection-pooled requests Session with exponential backoff retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=pool_maxsize, pool_maxsize=pool_maxsize)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_http_session(request: Request) -> requests.Session | None:
    """Retrieves shared connection-pooled HTTP session from FastAPI app state."""
    return getattr(request.app.state, "http_session", None)


def get_service(
    settings: Settings = Depends(get_settings),
    session: requests.Session | None = Depends(get_http_session),
) -> FeedService:
    """FastAPI dependency provider returning initialized FeedService."""
    return FeedService(settings=settings, session=session)


def _run[T](fn: Callable[[], T]) -> T:
    """Helper wrapper mapping FeedService domain exceptions to HTTP response status codes."""
    try:
        return fn()
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except UpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
