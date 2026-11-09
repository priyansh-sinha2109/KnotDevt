from fastapi.testclient import TestClient

from app.main import app


def test_health_and_migrated_dependencies() -> None:
    with TestClient(app) as client:
        for path in ("/health", "/api/v1/health"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            assert len(response.headers["X-Request-ID"]) == 32
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "postgres": True, "redis": True}
        assert client.get("/openapi.json").status_code == 200


def test_consistent_unknown_route() -> None:
    with TestClient(app) as client:
        response = client.get("/missing")
        assert response.status_code == 404
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
