import json

from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_provider
from app.llm import ToolCall
from app.main import create_app
from tests.auth_helpers import JWT_SECRET, PASSWORD, bearer, login, register
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response


def test_agent_run_list_includes_tools_without_secrets(clean_database: str) -> None:
    app = create_app(make_settings(database_url=clean_database, jwt_secret=JWT_SECRET))
    secret = "sk-live-do-not-store"
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        responses=[
            tool_call_response(
                ToolCall(
                    id="call_1",
                    name="calculator",
                    arguments=json.dumps({"expression": "2 + 2", "api_key": secret}),
                )
            ),
            answer_response("4"),
        ]
    )

    with TestClient(app) as client:
        admin = register(client, email="admin@example.com")
        created = client.post(
            "/api/v1/users",
            headers=bearer(admin["access_token"]),
            json={
                "email": "member@example.com",
                "name": "Member",
                "password": PASSWORD,
                "role": "user",
            },
        )
        assert created.status_code == 201
        chat = client.post(
            "/api/v1/chat",
            headers=bearer(login(client, "member@example.com")),
            json={"message": "What is 2 + 2?"},
        )
        assert chat.status_code == 200

        listed = client.get("/api/v1/agent-runs", headers=bearer(admin["access_token"]))

    assert listed.status_code == 200
    [run] = listed.json()
    assert run["status"] == "completed"
    assert run["final_answer"] == "4"
    assert run["started_at"]
    [call] = run["tool_calls"]
    assert call["tool_name"] == "calculator"
    assert call["status"] == "failed"
    assert call["arguments"]["expression"] == "2 + 2"
    assert call["arguments"]["api_key"] == "[redacted]"
    assert call["result_summary"].startswith("Failed:")
    assert secret not in listed.text
