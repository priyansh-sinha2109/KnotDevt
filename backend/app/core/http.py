import json
import logging
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger("uvicorn.error")


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    body = ErrorBody(code=code, message=message, request_id=request.state.request_id)
    return JSONResponse(body.model_dump(), status_code=status)


def install_http(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        response = error(request, exc.status_code, f"http_{exc.status_code}", message)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error(request, 422, "validation_error", "Request validation failed")

    @app.middleware("http")
    async def correlated(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.request_id = uuid4().hex
        started = monotonic()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                json.dumps(
                    {
                        "event": "request_failure",
                        "exception": type(exc).__name__,
                        "detail": str(exc).splitlines()[0][:240],
                        "request_id": request.state.request_id,
                    }
                )
            )
            response = error(
                request, 500, "internal_error", "An internal error occurred"
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("Cache-Control", "no-store")
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "method": request.method,
                    "route": getattr(route, "path", None),
                    "status": response.status_code,
                    "request_id": request.state.request_id,
                    "duration_ms": round((monotonic() - started) * 1000, 2),
                }
            )
        )
        return response
