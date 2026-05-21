from llm.llm_client import LLMClient


def test_prepare_openai_payload_skips_response_format_for_glm_models(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client, "provider", "openai")

    _, payload = client._prepare_openai_payload(
        current_messages=[{"role": "user", "content": "return json"}],
        model_name="glm-5.1",
        temperature=0.2,
        role="reflector",
        expect_json=True,
    )

    assert "response_format" not in payload


def test_prepare_openai_payload_keeps_response_format_for_deepseek(monkeypatch):
    client = LLMClient()
    monkeypatch.setattr(client, "provider", "openai")

    _, payload = client._prepare_openai_payload(
        current_messages=[{"role": "user", "content": "return json"}],
        model_name="deepseek-v4-pro",
        temperature=0.2,
        role="reflector",
        expect_json=True,
    )

    assert payload["response_format"] == {"type": "json_object"}
