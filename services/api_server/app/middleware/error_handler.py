from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common_schemas.exceptions import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)


_STATUS_MAP: dict[type[DomainError], int] = {
    ValidationError: 400,
    AuthorizationError: 403,
    NotFoundError: 404,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        status = next((code for cls, code in _STATUS_MAP.items() if isinstance(exc, cls)), 500)
        request_id = getattr(request.state, "request_id", None)
        if status >= 500:
            logger.exception("DomainError [%s]: %s", request_id, exc)
        return JSONResponse(
            status_code=status,
            content={
                "code": getattr(exc, "code", None) or exc.__class__.__name__,
                "message": str(exc),
                "request_id": request_id,
            },
        )
