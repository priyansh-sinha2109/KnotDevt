"""Minimal public edge for OAuth callbacks and signed connector webhooks.

This process is intentionally separate from the application server.  It binds
only to loopback and has a deny-by-default route allowlist so a tunnel cannot
reach private APIs, documentation, or admin endpoints.
"""

from __future__ import annotations

import re

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

UPSTREAM = "http://127.0.0.1:8080"
MAX_BODY = 1_048_576
CALLBACK = re.compile(r"^/api/v1/integrations/(github|slack|jira)/callback$")
WEBHOOK = re.compile(r"^/api/v1/integrations/webhooks/(github|slack)$")

app = FastAPI(
    title="KnotDevt public connector edge",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _forward_headers(request: Request) -> dict[str, str]:
    # Host is fixed to the local backend; forwarding it from the public tunnel
    # would make callback URL and origin handling ambiguous.
    excluded = {"host", "content-length", "connection"}
    return {k: v for k, v in request.headers.items() if k.lower() not in excluded}


async def _proxy(request: Request, path: str) -> Response:
    body = b""
    if request.method == "POST":
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY:
                return JSONResponse({"detail": "Webhook is too large"}, status_code=413)
            body += chunk
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            upstream = await client.request(
                request.method,
                UPSTREAM + path,
                params=request.query_params,
                content=body,
                headers=_forward_headers(request),
            )
    except httpx.RequestError:
        return JSONResponse(
            {"detail": "Connector backend unavailable"}, status_code=502
        )

    # Preserve redirects and provider verification responses, but do not leak
    # hop-by-hop headers from the internal server.
    hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
    headers = {k: v for k, v in upstream.headers.items() if k.lower() not in hop}
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
        media_type=upstream.headers.get("content-type"),
    )


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def allowlisted_edge(request: Request, path: str) -> Response:
    path = "/" + path
    if request.method == "GET" and CALLBACK.fullmatch(path):
        return await _proxy(request, path)
    if request.method == "POST" and WEBHOOK.fullmatch(path):
        return await _proxy(request, path)
    return JSONResponse({"detail": "Not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8090, access_log=False)
