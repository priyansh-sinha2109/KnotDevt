from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, projects
from app.core.config import settings
from app.core.http import install_http


def create_app() -> FastAPI:
    app = FastAPI(title="KnotDevt", version="0.1.0")
    api = APIRouter(prefix="/api/v1")
    api.add_api_route("/health", health.health, methods=["GET"], tags=["health"])
    app.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(projects.router)
    app.include_router(api)
    install_http(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings().allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "If-Match"],
        expose_headers=["X-Request-ID"],
    )
    return app


app = create_app()
