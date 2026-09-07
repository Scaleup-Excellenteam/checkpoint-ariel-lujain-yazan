"""Provider-independent DLP classification core.

The injected provider callable receives the untrusted message and protected
reference as separate keyword arguments. It must return a JSON object string
containing only an ``action`` field. This module never logs those inputs or the
raw provider response.
"""

from collections.abc import Awaitable, Callable
from enum import Enum
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError


class DlpDecision(BaseModel):
    """The complete set of fields trusted from a model response."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: Literal["ALLOW", "BLOCK"]


class DlpFailureKind(str, Enum):
    TIMEOUT = "TIMEOUT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    UNAVAILABLE = "UNAVAILABLE"


class DlpFailure(RuntimeError):
    """A controlled failure that contains no provider or protected content."""

    def __init__(self, kind: DlpFailureKind):
        self.kind = kind
        super().__init__(f"DLP classification failed: {kind.value}")


DlpProviderCall = Callable[..., Awaitable[str]]


class _DuplicateJsonKey(ValueError):
    pass


def _object_without_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def parse_model_output(raw_output: str) -> DlpDecision:
    """Parse a strict JSON decision or raise a sanitized controlled failure."""
    if type(raw_output) is not str:
        raise DlpFailure(DlpFailureKind.MALFORMED_RESPONSE)

    try:
        parsed_output = json.loads(
            raw_output,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        decision = DlpDecision.model_validate(parsed_output, strict=True)
    except (ValidationError, ValueError, TypeError):
        malformed = True
    else:
        malformed = False

    if malformed:
        raw_output = None
        parsed_output = None
        raise DlpFailure(DlpFailureKind.MALFORMED_RESPONSE)

    return decision


class DlpClassifier:
    """Validate the result of an injected asynchronous DLP provider call."""

    def __init__(
        self,
        provider_call: DlpProviderCall | None,
        protected_context: str | None,
    ):
        self._provider_call = provider_call
        self._protected_context = protected_context

    async def classify(self, message: str) -> DlpDecision:
        if (
            self._provider_call is None
            or not isinstance(self._protected_context, str)
            or not self._protected_context.strip()
        ):
            raise DlpFailure(DlpFailureKind.UNAVAILABLE)

        failure_kind = None
        try:
            raw_output = await self._provider_call(
                message=message,
                protected_context=self._protected_context,
            )
        except DlpFailure:
            raise
        except TimeoutError:
            failure_kind = DlpFailureKind.TIMEOUT
        except Exception:
            failure_kind = DlpFailureKind.PROVIDER_FAILURE

        if failure_kind is not None:
            raise DlpFailure(failure_kind)

        return parse_model_output(raw_output)
