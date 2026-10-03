from app.agent.presentation import present_arguments, summarize_tool_result


def test_arguments_redact_secret_keys_and_secret_values() -> None:
    arguments = present_arguments(
        {
            "expression": "2 + 2",
            "api_key": "sk-live-should-not-appear",
            "note": "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
        }
    )

    assert arguments["expression"] == "2 + 2"
    assert arguments["api_key"] == "[redacted]"
    assert "sk-live" not in arguments["note"]
    assert "[redacted]" in arguments["note"]


def test_calculator_summary_is_the_result() -> None:
    assert summarize_tool_result("calculator", {"result": 4}) == "4"


def test_failed_tool_summary_does_not_include_a_secret() -> None:
    summary = summarize_tool_result(
        "calculator",
        {"error": "provider failed: sk-live-do-not-store"},
    )

    assert summary is not None
    assert summary.startswith("Failed:")
    assert "sk-live" not in summary


def test_knowledge_summary_names_documents_and_omits_passages() -> None:
    excerpt = "The refund window is 30 days and this sentence must not be copied into the summary."
    summary = summarize_tool_result(
        "search_knowledge",
        {
            "results": [
                {"document": "policy.md", "chunk": excerpt, "similarity": 0.9},
                {"document": "policy.md", "chunk": "Another private passage.", "similarity": 0.8},
                {"document": "shipping.txt", "chunk": "Ships in two days.", "similarity": 0.7},
            ]
        },
    )

    assert summary == "3 passages from policy.md, shipping.txt."
    assert "refund window" not in summary
    assert excerpt not in (summary or "")


def test_knowledge_summary_when_nothing_matched() -> None:
    assert summarize_tool_result("search_knowledge", {"results": []}) == "No matching passages."


def test_analytics_summary_counts_rows_without_customer_names() -> None:
    summary = summarize_tool_result(
        "analytics",
        {
            "operation": "get_top_customers",
            "customers": [{"name": "Ada Lovelace", "total_spent": "10.00"}],
        },
    )

    assert summary == "get_top_customers: 1 customer."
    assert "Ada" not in (summary or "")


def test_missing_result_has_no_summary() -> None:
    assert summarize_tool_result("calculator", None) is None
