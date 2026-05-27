"""Domain exceptions for the backend layer.

Every error raised by a :class:`persona.backends.protocol.ChatBackend`
implementation is a subclass of :class:`ProviderError`, which in turn is a
subclass of :class:`persona.errors.PersonaError`. Provider-specific exceptions
from third-party SDKs (``anthropic``, ``openai``, ``httpx``) are caught at the
adapter boundary and re-raised through this hierarchy so callers depend on
our types rather than on a transitive dependency.

See ``docs/specs/spec_02/decisions.md`` D-02-1 for the
``BackendTimeoutError`` rationale and D-02-8 for ``retry_after_s`` semantics.
"""

from __future__ import annotations

from persona.errors import PersonaError

__all__ = [
    "AuthenticationError",
    "BackendTimeoutError",
    "ModelNotFoundError",
    "ProviderError",
    "RateLimitError",
]


class ProviderError(PersonaError):
    """Base for every backend-raised error.

    Non-retryable by default. Subclasses signal specific retry semantics
    (``RateLimitError`` carries an optional ``retry_after_s`` in ``context``;
    ``BackendTimeoutError`` is the canonical retry target).

    Implementations should always populate ``context`` with at least
    ``provider`` and (when known) ``model`` so log messages are structured.
    """


class AuthenticationError(ProviderError):
    """Raised when an API key is missing, invalid, or rejected by the provider.

    Backends raise this at construction time when the configured key is
    missing or empty (fail fast — see spec §10 #8), and at call time when
    the provider returns 401 / 403.
    """


class RateLimitError(ProviderError):
    """Raised when the provider returns 429 (or equivalent).

    When the provider supplies a ``retry-after`` header, it is recorded in
    ``context["retry_after_s"]`` as a string of integer seconds. The header
    is the only source — we never invent a default (D-02-8).
    """


class ModelNotFoundError(ProviderError):
    """Raised when the configured model name is unknown to the provider.

    Maps Anthropic / OpenAI ``NotFoundError`` (model variant) and Ollama's
    ``404 {"error": "model 'xxx' not found"}`` response.
    """


class BackendTimeoutError(ProviderError):
    """Raised when an HTTP request to the provider times out.

    Maps ``httpx.TimeoutException``, ``anthropic.APITimeoutError``, and
    ``openai.APITimeoutError``. Distinct from :class:`ProviderError` because
    timeouts are the most common transient failure callers retry on
    (D-02-1).
    """
