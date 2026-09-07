import asyncio

import pytest

from server.dlp import (
    DlpClassifier,
    DlpDecision,
    DlpFailure,
    DlpFailureKind,
    parse_model_output,
)


@pytest.mark.parametrize("action", ["ALLOW", "BLOCK"])
def test_valid_action_is_accepted(action):
    assert parse_model_output(f'{{"action":"{action}"}}') == DlpDecision(
        action=action,
    )


@pytest.mark.parametrize(
    "raw_output",
    [
        '{"action":"REVIEW"}',
        "ALLOW",
        '```json\n{"action":"ALLOW"}\n```',
        "{}",
        '{"action":"BLOCK","reason":"SENSITIVE_CONTENT"}',
        '{"action":"ALLOW"',
        '[{"action":"ALLOW"}]',
        '{"action":"ALLOW"} trailing',
        '{"action":"ALLOW"}{"action":"BLOCK"}',
        "null",
        '"ALLOW"',
        "1",
        '{"action":"allow"}',
        '{"action":"block"}',
        None,
    ],
    ids=[
        "unknown-action",
        "free-form-text",
        "markdown-wrapped",
        "missing-action",
        "extra-field",
        "malformed-json",
        "wrong-json-shape",
        "trailing-content",
        "multiple-json-objects",
        "json-null",
        "json-string",
        "json-number",
        "lowercase-allow",
        "lowercase-block",
        "non-text-output",
    ],
)
def test_invalid_model_output_is_a_controlled_failure(raw_output):
    with pytest.raises(DlpFailure) as exc_info:
        parse_model_output(raw_output)

    assert exc_info.value.kind is DlpFailureKind.MALFORMED_RESPONSE
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    "raw_output",
    [
        '{"action":"BLOCK","action":"ALLOW"}',
        '{"action":"ALLOW","action":"ALLOW"}',
    ],
)
def test_duplicate_json_keys_are_rejected(raw_output):
    with pytest.raises(DlpFailure) as exc_info:
        parse_model_output(raw_output)

    assert exc_info.value.kind is DlpFailureKind.MALFORMED_RESPONSE
    assert exc_info.value.__context__ is None


def test_classifier_passes_separate_message_and_protected_context():
    received = {}

    async def fake_provider_call(*, message, protected_context):
        received["message"] = message
        received["protected_context"] = protected_context
        return '{"action":"BLOCK"}'

    classifier = DlpClassifier(
        provider_call=fake_provider_call,
        protected_context="server-only reference",
    )

    decision = asyncio.run(classifier.classify("untrusted chat message"))

    assert decision == DlpDecision(action="BLOCK")
    assert received == {
        "message": "untrusted chat message",
        "protected_context": "server-only reference",
    }


@pytest.mark.parametrize(
    ("provider_error", "expected_kind"),
    [
        (TimeoutError("request contained protected text"), DlpFailureKind.TIMEOUT),
        (RuntimeError("API key and raw response"), DlpFailureKind.PROVIDER_FAILURE),
    ],
)
def test_provider_failure_becomes_controlled_failure(provider_error, expected_kind):
    async def failing_provider_call(**_):
        raise provider_error

    classifier = DlpClassifier(
        provider_call=failing_provider_call,
        protected_context="server-only reference",
    )

    with pytest.raises(DlpFailure) as exc_info:
        asyncio.run(classifier.classify("untrusted chat message"))

    assert exc_info.value.kind is expected_kind
    assert "protected text" not in str(exc_info.value)
    assert "API key" not in str(exc_info.value)
    assert vars(exc_info.value) == {"kind": expected_kind}
    assert exc_info.value.__context__ is None


def test_malformed_provider_result_is_never_converted_to_allow():
    async def malformed_provider_call(**_):
        return "The message is probably safe."

    classifier = DlpClassifier(
        provider_call=malformed_provider_call,
        protected_context="server-only reference",
    )

    with pytest.raises(DlpFailure) as exc_info:
        asyncio.run(classifier.classify("untrusted chat message"))

    assert exc_info.value.kind is DlpFailureKind.MALFORMED_RESPONSE
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    "raw_output",
    [None, b'{"action":"ALLOW"}', {"action": "ALLOW"}, ["ALLOW"], 1],
    ids=["none", "bytes", "dict", "list", "integer"],
)
def test_wrong_provider_return_type_is_a_controlled_failure(raw_output):
    async def wrong_type_provider_call(**_):
        return raw_output

    classifier = DlpClassifier(
        provider_call=wrong_type_provider_call,
        protected_context="server-only reference",
    )

    with pytest.raises(DlpFailure) as exc_info:
        asyncio.run(classifier.classify("untrusted chat message"))

    assert exc_info.value.kind is DlpFailureKind.MALFORMED_RESPONSE
    assert exc_info.value.__context__ is None


def test_provider_cancellation_propagates():
    async def cancelled_provider_call(**_):
        raise asyncio.CancelledError

    classifier = DlpClassifier(
        provider_call=cancelled_provider_call,
        protected_context="server-only reference",
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(classifier.classify("untrusted chat message"))


def test_classifier_can_be_reused_after_provider_failure():
    call_count = 0

    async def recovering_provider_call(**_):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("sensitive provider details")
        return '{"action":"ALLOW"}'

    classifier = DlpClassifier(
        provider_call=recovering_provider_call,
        protected_context="server-only reference",
    )

    async def classify_twice():
        with pytest.raises(DlpFailure) as exc_info:
            await classifier.classify("first message")
        decision = await classifier.classify("second message")
        return exc_info.value, decision

    error, decision = asyncio.run(classify_twice())

    assert error.kind is DlpFailureKind.PROVIDER_FAILURE
    assert error.__context__ is None
    assert decision == DlpDecision(action="ALLOW")
    assert call_count == 2


@pytest.mark.parametrize(
    ("provider_call", "protected_context"),
    [
        (None, "server-only reference"),
        (lambda **_: None, None),
        (lambda **_: None, "   "),
    ],
)
def test_unavailable_classifier_fails_in_a_controlled_way(
    provider_call,
    protected_context,
):
    classifier = DlpClassifier(
        provider_call=provider_call,
        protected_context=protected_context,
    )

    with pytest.raises(DlpFailure) as exc_info:
        asyncio.run(classifier.classify("untrusted chat message"))

    assert exc_info.value.kind is DlpFailureKind.UNAVAILABLE
