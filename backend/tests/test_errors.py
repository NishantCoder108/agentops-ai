from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppError


def test_unknown_route_uses_error_format(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None}
    }


def test_method_not_allowed_uses_error_format(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_app_error_uses_error_format(app: FastAPI, client: TestClient) -> None:
    @app.get("/boom-app")
    async def boom_app() -> None:
        raise AppError("Thing is broken", code="thing_broken", status_code=409, details={"id": 1})

    response = client.get("/boom-app")

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "thing_broken", "message": "Thing is broken", "details": {"id": 1}}
    }


def test_validation_error_uses_error_format(app: FastAPI, client: TestClient) -> None:
    @app.get("/needs-int")
    async def needs_int(value: int) -> dict:
        return {"value": value}

    response = client.get("/needs-int", params={"value": "abc"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["query", "value"]


def test_unhandled_error_hides_internals(app: FastAPI, client: TestClient) -> None:
    @app.get("/boom-unhandled")
    async def boom_unhandled() -> None:
        raise RuntimeError("secret internal detail")

    response = client.get("/boom-unhandled")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred",
            "details": None,
        }
    }
