"""Tests for ``persona.imagegen.nvidia_image`` (Spec 20 T10).

Mocked-SDK + mocked-httpx tests for :class:`NvidiaImageBackend`. Covers:

* Construction-time guards: missing/empty API key, wrong provider,
  D-20-X-flux-1-dev-license-block (FLUX.1-dev + FLUX.1-kontext-dev),
  unknown model.
* Branch B (OpenAI-compat) happy path through the openai SDK against a
  custom ``base_url``.
* Branch B error mapping: 401 → :class:`ImageGenUnavailableError`,
  429 → ``rate_limit``, 402 ``credits_expired`` body →
  :class:`ImageProviderError(reason="credits_expired")` so T16 (D-20-9)
  treats it as a FALLBACK trigger.
* Branch A (legacy GenAI) happy path against
  ``ai.api.nvidia.com/v1/genai/...`` using ``httpx.MockTransport``.
* Branch A NVCF async path: HTTP 202 + ``NVCF-REQID`` header → poll →
  eventual 200.
* Branch A error mapping: 429 → ``rate_limit``, 401 → auth, 402
  ``credits_expired`` → ``credits_expired``.

No real network; no real credentials.
"""

# ruff: noqa: ANN401, SLF001 — mocks use Any return types; tests access private attrs

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest
from persona.imagegen import (
    ContentRejectedError,
    ImageBackend,
    ImageBackendConfig,
    ImageGenOptions,
    ImageGenUnavailableError,
    ImageProviderError,
    NvidiaImageBackend,
)
from persona.imagegen.nvidia_image import (
    _BRANCH_A_MODELS,
    _BRANCH_B_MODELS,
    _LICENCE_BLOCKED_MODELS,
    _branch_a_endpoint,
)
from pydantic import SecretStr

# Capture the real ``httpx.AsyncClient`` so MockTransport injection
# does not recurse when the lambda factory re-enters the patched name.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _config(
    *,
    model: str,
    api_key: str | None = "test-key",
    timeout: float = 60.0,
) -> ImageBackendConfig:
    return ImageBackendConfig(
        provider="nvidia",
        model=model,
        api_key=SecretStr(api_key) if api_key is not None else None,
        request_timeout_s=timeout,
    )


def _b64(payload: bytes) -> str:
    import base64

    return base64.b64encode(payload).decode("ascii")


@pytest.fixture
def png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\nfake-image-bytes-for-tests"


# ---------------------------------------------------------------------------
# Construction-time guards
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_construct_branch_b_model_ok(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/flux.2-klein-4b"))
        assert backend.provider_name == "nvidia"
        assert backend.model_name == "nvidia/flux.2-klein-4b"
        assert backend._branch == "B"
        assert backend._openai_client is not None

    def test_construct_branch_a_model_ok(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))
        assert backend._branch == "A"
        # Branch A does NOT allocate an openai client.
        assert backend._openai_client is None

    def test_protocol_membership(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/qwen-image"))
        assert isinstance(backend, ImageBackend)

    def test_missing_api_key_raises_unavailable(self) -> None:
        with pytest.raises(ImageGenUnavailableError) as exc_info:
            NvidiaImageBackend(_config(model="nvidia/qwen-image", api_key=None))
        assert exc_info.value.context["reason"] == "missing_api_key"

    def test_empty_api_key_raises_unavailable(self) -> None:
        with pytest.raises(ImageGenUnavailableError) as exc_info:
            NvidiaImageBackend(_config(model="nvidia/qwen-image", api_key=""))
        assert exc_info.value.context["reason"] == "missing_api_key"

    def test_wrong_provider_raises_provider_error(self) -> None:
        config = ImageBackendConfig(provider="openai", model="gpt-image-1", api_key=SecretStr("k"))
        with pytest.raises(ImageProviderError) as exc_info:
            NvidiaImageBackend(config)
        assert exc_info.value.context["provider"] == "openai"

    @pytest.mark.parametrize(
        "model",
        [
            "nvidia/black-forest-labs/flux.1-dev",
            "nvidia/black-forest-labs/flux.1-kontext-dev",
        ],
    )
    def test_flux_1_dev_license_block_at_construction(self, model: str) -> None:
        # D-20-X-flux-1-dev-license-block: construction MUST refuse so
        # the operator sees the stop-block at startup, not on first call.
        with pytest.raises(ImageProviderError) as exc_info:
            NvidiaImageBackend(_config(model=model))
        ctx = exc_info.value.context
        assert ctx["reason"] == "non_commercial_license"
        assert ctx["model"] == model
        assert ctx["provider"] == "nvidia"
        # Hint text steers operators to commercial-clean alternatives.
        assert "flux.2-klein-4b" in ctx["hint"]

    def test_unknown_model_raises_unsupported(self) -> None:
        with pytest.raises(ImageProviderError) as exc_info:
            NvidiaImageBackend(_config(model="nvidia/not-a-real-model"))
        ctx = exc_info.value.context
        assert ctx["reason"] == "unsupported_model"
        assert ctx["model"] == "nvidia/not-a-real-model"
        # Supported list helps operators recover quickly.
        assert "nvidia/qwen-image" in ctx["supported"]

    def test_dispatch_tables_disjoint(self) -> None:
        # Sanity: a model lives in exactly one branch; licence-blocked
        # set is disjoint from both branches (operators can never reach
        # a blocked model by changing dispatch).
        assert _BRANCH_A_MODELS.isdisjoint(_BRANCH_B_MODELS)
        assert _LICENCE_BLOCKED_MODELS.isdisjoint(_BRANCH_A_MODELS)
        assert _LICENCE_BLOCKED_MODELS.isdisjoint(_BRANCH_B_MODELS)


# ---------------------------------------------------------------------------
# Branch B — OpenAI-compat
# ---------------------------------------------------------------------------


def _mock_image_response(*, b64: str, count: int = 1) -> Any:
    response = MagicMock()
    response.data = [MagicMock(b64_json=b64) for _ in range(count)]
    return response


class TestBranchBOpenAICompat:
    """Branch B targets ``integrate.api.nvidia.com/v1/images/generations``."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_image_bytes(self, png_bytes: bytes) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/flux.2-klein-4b"))
        fake_response = _mock_image_response(b64=_b64(png_bytes), count=1)
        assert backend._openai_client is not None
        backend._openai_client.images.generate = AsyncMock(  # type: ignore[method-assign]
            return_value=fake_response
        )

        result = await backend.generate("a red bicycle")

        assert result.provider == "nvidia"
        assert result.model == "nvidia/flux.2-klein-4b"
        assert len(result.images) == 1
        assert result.images[0].image_bytes == png_bytes
        assert result.images[0].media_type == "image/png"
        assert result.images[0].width == 1024
        assert result.images[0].height == 1024
        assert result.latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_count_two_returns_two_images(self, png_bytes: bytes) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/qwen-image"))
        fake_response = _mock_image_response(b64=_b64(png_bytes), count=2)
        assert backend._openai_client is not None
        backend._openai_client.images.generate = AsyncMock(  # type: ignore[method-assign]
            return_value=fake_response
        )

        result = await backend.generate("a cat", options=ImageGenOptions(size="1024x1024", count=2))
        assert len(result.images) == 2
        assert all(img.image_bytes == png_bytes for img in result.images)

    @pytest.mark.asyncio
    async def test_401_auth_maps_to_unavailable(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/flux.2-klein-4b"))
        assert backend._openai_client is not None

        async def raise_auth(**_kwargs: Any) -> Any:
            response = MagicMock(status_code=401, headers={}, request=MagicMock())
            raise openai.AuthenticationError(message="bad key", response=response, body=None)

        backend._openai_client.images.generate = raise_auth  # type: ignore[method-assign]
        with pytest.raises(ImageGenUnavailableError) as exc_info:
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "auth"

    @pytest.mark.asyncio
    async def test_429_rate_limit_maps_to_provider_error(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/flux.2-klein-4b"))
        assert backend._openai_client is not None

        async def raise_rate_limit(**_kwargs: Any) -> Any:
            response = MagicMock(
                status_code=429, headers={"retry-after": "30"}, request=MagicMock()
            )
            raise openai.RateLimitError(message="rl", response=response, body=None)

        backend._openai_client.images.generate = raise_rate_limit  # type: ignore[method-assign]
        with pytest.raises(ImageProviderError) as exc_info:
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "rate_limit"
        assert exc_info.value.context["retry_after_s"] == "30"

    @pytest.mark.asyncio
    async def test_402_credits_expired_maps_to_credits_expired(self) -> None:
        # T16 (D-20-9) treats credits_expired as a FALLBACK trigger.
        backend = NvidiaImageBackend(_config(model="nvidia/flux.2-klein-4b"))
        assert backend._openai_client is not None

        async def raise_402(**_kwargs: Any) -> Any:
            response = MagicMock(status_code=402, headers={}, request=MagicMock())
            raise openai.APIStatusError(
                message="402",
                response=response,
                body={
                    "type": "about:blank",
                    "title": "Cloud Credits Expired",
                    "status": 402,
                    "detail": "Your NVIDIA credits have expired.",
                },
            )

        backend._openai_client.images.generate = raise_402  # type: ignore[method-assign]
        with pytest.raises(ImageProviderError) as exc_info:
            await backend.generate("a cat")
        ctx = exc_info.value.context
        assert ctx["reason"] == "credits_expired"
        assert ctx["provider"] == "nvidia"
        assert ctx["status"] == "402"

    @pytest.mark.asyncio
    async def test_empty_data_array_maps_to_transient(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/qwen-image"))
        fake_response = MagicMock()
        fake_response.data = []
        assert backend._openai_client is not None
        backend._openai_client.images.generate = AsyncMock(  # type: ignore[method-assign]
            return_value=fake_response
        )
        with pytest.raises(ImageProviderError) as exc_info:
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "transient"

    @pytest.mark.asyncio
    async def test_missing_b64_json_maps_to_transient(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/qwen-image"))
        entry = MagicMock(b64_json=None)
        fake_response = MagicMock()
        fake_response.data = [entry]
        assert backend._openai_client is not None
        backend._openai_client.images.generate = AsyncMock(  # type: ignore[method-assign]
            return_value=fake_response
        )
        with pytest.raises(ImageProviderError) as exc_info:
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "transient"

    @pytest.mark.asyncio
    async def test_timeout_maps_to_timeout(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/qwen-image"))
        assert backend._openai_client is not None

        async def raise_timeout(**_kwargs: Any) -> Any:
            raise openai.APITimeoutError(request=httpx.Request("POST", "x"))

        backend._openai_client.images.generate = raise_timeout  # type: ignore[method-assign]
        with pytest.raises(ImageProviderError) as exc_info:
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "timeout"


# ---------------------------------------------------------------------------
# Branch A — Legacy GenAI
# ---------------------------------------------------------------------------


def _branch_a_request_filter(expected_url: str) -> Any:
    """Build a check that ``request.url`` matches the Branch A endpoint."""

    def matches(request: httpx.Request) -> bool:
        return str(request.url) == expected_url

    return matches


class TestBranchALegacyGenAI:
    """Branch A targets ``ai.api.nvidia.com/v1/genai/{vendor}/{model}``."""

    @pytest.mark.asyncio
    async def test_endpoint_helper_strips_nvidia_prefix(self) -> None:
        # The hosted catalog id is ``nvidia/{vendor}/{model}``; the GenAI
        # endpoint expects the ``/v1/genai/{vendor}/{model}`` shape.
        assert _branch_a_endpoint("nvidia/stabilityai/stable-diffusion-xl") == (
            "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-xl"
        )

    @pytest.mark.asyncio
    async def test_happy_path_returns_artifacts(self, png_bytes: bytes) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))
        endpoint = _branch_a_endpoint(backend.model_name)
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == endpoint and request.method == "POST":
                import json as _json

                captured["body"] = _json.loads(request.content.decode("utf-8"))
                captured["auth"] = request.headers.get("Authorization")
                return httpx.Response(
                    200,
                    json={"artifacts": [{"base64": _b64(png_bytes), "finishReason": "SUCCESS"}]},
                )
            return httpx.Response(404)

        with patch(
            "persona.imagegen.nvidia_image.httpx.AsyncClient",
            lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
        ):
            result = await backend.generate("a red bicycle")

        assert result.provider == "nvidia"
        assert result.model == "nvidia/stabilityai/stable-diffusion-xl"
        assert len(result.images) == 1
        assert result.images[0].image_bytes == png_bytes
        # Body shape: NVIDIA-specific text_prompts + cfg_scale + mode.
        body = captured["body"]
        assert body["text_prompts"] == [{"text": "a red bicycle", "weight": 1.0}]
        assert body["mode"] == "text-to-image"
        assert body["width"] == 1024
        assert body["height"] == 1024
        assert body["samples"] == 1
        # Auth header carries the configured API key.
        assert captured["auth"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_nvcf_async_poll_to_terminal_200(self, png_bytes: bytes) -> None:
        # Branch A returns 202 + NVCF-REQID; the backend polls
        # /v2/nvcf/pexec/status/{reqId} until a 200 lands.
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))
        endpoint = _branch_a_endpoint(backend.model_name)
        status_url = "https://ai.api.nvidia.com/v2/nvcf/pexec/status/req-abc-123"

        call_count = {"poll": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url == endpoint and request.method == "POST":
                return httpx.Response(
                    202,
                    headers={"NVCF-REQID": "req-abc-123", "NVCF-POLL-SECONDS": "0"},
                )
            if url == status_url and request.method == "GET":
                call_count["poll"] += 1
                if call_count["poll"] < 2:
                    # Still pending — return 202 once more.
                    return httpx.Response(
                        202,
                        headers={
                            "NVCF-REQID": "req-abc-123",
                            "NVCF-POLL-SECONDS": "0",
                        },
                    )
                return httpx.Response(
                    200,
                    json={"artifacts": [{"base64": _b64(png_bytes)}]},
                )
            return httpx.Response(404)

        with patch(
            "persona.imagegen.nvidia_image.httpx.AsyncClient",
            lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
        ):
            result = await backend.generate("a cat")
        assert call_count["poll"] >= 1
        assert result.images[0].image_bytes == png_bytes

    @pytest.mark.asyncio
    async def test_202_without_reqid_maps_to_transient(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(202, headers={})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "transient"

    @pytest.mark.asyncio
    async def test_401_auth_maps_to_unavailable(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "invalid key"})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageGenUnavailableError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "auth"

    @pytest.mark.asyncio
    async def test_429_rate_limit_maps_to_provider_error(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"retry-after": "12"}, json={})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "rate_limit"
        assert exc_info.value.context["retry_after_s"] == "12"

    @pytest.mark.asyncio
    async def test_402_credits_expired_maps_to_credits_expired(self) -> None:
        # T16 (D-20-9) fallback trigger — distinct from generic 402.
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                402,
                json={
                    "type": "about:blank",
                    "title": "Cloud Credits Expired",
                    "status": 402,
                    "detail": "Your account has used all credits.",
                },
            )

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        ctx = exc_info.value.context
        assert ctx["reason"] == "credits_expired"
        assert ctx["provider"] == "nvidia"

    @pytest.mark.asyncio
    async def test_402_non_credits_maps_to_transient(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                402,
                json={
                    "type": "about:blank",
                    "title": "Payment Required",
                    "detail": "Subscription inactive.",
                },
            )

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        # Non-credits 402 falls back to transient — keeps the discriminator
        # honest so only the literal "credits expired" case triggers T16
        # fallback.
        assert exc_info.value.context["reason"] == "transient"

    @pytest.mark.asyncio
    async def test_422_maps_to_content_rejected(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"detail": "content policy violation"})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ContentRejectedError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "provider_moderation"
        assert exc_info.value.context["stage"] == "input"

    @pytest.mark.asyncio
    async def test_500_maps_to_transient(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "transient"
        assert exc_info.value.context["status"] == "500"

    @pytest.mark.asyncio
    async def test_empty_artifacts_maps_to_transient(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"artifacts": []})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "transient"

    @pytest.mark.asyncio
    async def test_artifact_missing_base64_maps_to_transient(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"artifacts": [{"finishReason": "SUCCESS"}]})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "transient"

    @pytest.mark.asyncio
    async def test_timeout_exception_maps_to_timeout(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out")

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError) as exc_info,
        ):
            await backend.generate("a cat")
        assert exc_info.value.context["reason"] == "timeout"


# ---------------------------------------------------------------------------
# D-20-14 atomic generate() semantics
# ---------------------------------------------------------------------------


class TestAtomicGenerate:
    """generate() returns a complete GenerationResult OR raises — never partial."""

    @pytest.mark.asyncio
    async def test_branch_b_success_returns_complete_result(self, png_bytes: bytes) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/qwen-image-2512"))
        fake_response = _mock_image_response(b64=_b64(png_bytes), count=2)
        assert backend._openai_client is not None
        backend._openai_client.images.generate = AsyncMock(  # type: ignore[method-assign]
            return_value=fake_response
        )
        result = await backend.generate("a cat", options=ImageGenOptions(count=2))
        assert len(result.images) == 2
        # Provider + model + latency all populated (no partial state).
        assert result.provider == "nvidia"
        assert result.model == "nvidia/qwen-image-2512"
        assert result.latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_failure_raises_domain_error_no_partial_result(self) -> None:
        backend = NvidiaImageBackend(_config(model="nvidia/stabilityai/stable-diffusion-xl"))

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={})

        with (
            patch(
                "persona.imagegen.nvidia_image.httpx.AsyncClient",
                lambda **kw: _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw),
            ),
            pytest.raises(ImageProviderError),
        ):
            await backend.generate("a cat")
        # No state to assert — generate() never yields a partial
        # GenerationResult, it raises (atomic per D-20-14).


# ---------------------------------------------------------------------------
# edit() — Protocol default delegates to NotImplementedError
# ---------------------------------------------------------------------------


class TestEditNotImplemented:
    @pytest.mark.asyncio
    async def test_edit_raises_not_implemented(self, png_bytes: bytes) -> None:
        from persona.imagegen.result import GeneratedImage

        backend = NvidiaImageBackend(_config(model="nvidia/qwen-image"))
        img = GeneratedImage(image_bytes=png_bytes, media_type="image/png", width=1024, height=1024)
        with pytest.raises(NotImplementedError):
            await backend.edit(img, "make it red")
