import json

from app.agent.tracking import redact, structured_json


def test_invalid_json_is_stored_as_raw_text() -> None:
    assert structured_json("not json") == {"raw": "not json"}
    assert structured_json("") == {}


def test_secret_keys_are_redacted_nested() -> None:
    value = structured_json(
        json.dumps(
            {
                "expression": "1 + 1",
                "api_key": "sk-secret",
                "nested": {"access_token": "tok", "name": "Ada"},
            }
        )
    )

    assert value["expression"] == "1 + 1"
    assert value["api_key"] == "[redacted]"
    assert value["nested"] == {"access_token": "[redacted]", "name": "Ada"}
    assert "sk-secret" not in json.dumps(value)


def test_redact_leaves_ordinary_values_alone() -> None:
    assert redact({"customer": "secret shop"}) == {"customer": "secret shop"}
