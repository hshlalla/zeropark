import pytest

from zeropark_core.llm import (
    ChatMessage,
    OpenAILLMClient,
    compress_messages,
    create_llm_client,
)


def test_compress_keeps_short_conversations_intact():
    msgs = [ChatMessage(role="system", content="sys")] + [
        ChatMessage(role="user", content=f"m{i}") for i in range(5)
    ]
    assert compress_messages(msgs, max_history=20) == msgs


def test_compress_folds_old_messages_into_digest():
    msgs = [ChatMessage(role="system", content="sys")] + [
        ChatMessage(role="user", content=f"message-{i}") for i in range(30)
    ]
    out = compress_messages(msgs, max_history=10)
    assert out[0].role == "system"
    digest = out[1]
    assert "auto-compressed" in digest.content
    assert "message-0" in digest.content       # early context preserved in digest
    assert len(out) == 1 + 1 + 10              # system + digest + recent 10
    assert out[-1].content == "message-29"


def test_openai_client_rejects_dummy_key():
    with pytest.raises(ValueError):
        OpenAILLMClient(api_key="dummy_key")
    with pytest.raises(ValueError):
        OpenAILLMClient(api_key="")


def test_factory_rejects_missing_key():
    with pytest.raises(ValueError):
        create_llm_client("openai", "")
