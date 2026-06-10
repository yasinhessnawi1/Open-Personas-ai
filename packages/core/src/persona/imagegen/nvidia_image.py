"""NVIDIA image-generation backend (Spec 20 T10).

Concrete :class:`persona.imagegen.protocol.ImageBackend` for the NVIDIA
Build Catalog. NVIDIA exposes TWO coexisting image-gen API shapes per
R-20-3 / D-20-1 and this single backend dispatches between them based on
the configured ``model`` token:

* **Branch B — OpenAI-compat** at ``https://integrate.api.nvidia.com/v1/``
  for ``nvidia/flux.2-klein-4b``, ``nvidia/qwen-image``,
  ``nvidia/qwen-image-2512``. The standard openai SDK targets this
  endpoint with a custom ``base_url``; the response shape is the
  familiar ``{"data": [{"b64_json": "..."}]}``.
* **Branch A — Legacy GenAI** at
  ``https://ai.api.nvidia.com/v1/genai/{vendor}/{model}`` for the
  commercial-clean SDXL path
  (``nvidia/stabilityai/stable-diffusion-xl``). The body shape is
  NVIDIA-specific (``text_prompts: [{text, weight}]``, ``cfg_scale``,
  ``sampler``, ``steps``, ``seed``, ``samples``, ``height``, ``width``,
  ``mode``); the response carries ``{"artifacts": [{"base64": "..."}]}``
  (literal field name ``base64`` — NOT ``b64_json``). NVCF may return
  HTTP 202 + ``NVCF-REQID`` header; the backend polls
  ``/v2/nvcf/pexec/status/{reqId}`` per spec until a 200 lands.

Three guards are load-bearing:

* **D-20-X-flux-1-dev-license-block.** ``nvidia/black-forest-labs/flux.1-dev``
  and ``nvidia/black-forest-labs/flux.1-kontext-dev`` are NON-commercial
  models on the hosted catalog. The constructor rejects them with
  :class:`ImageProviderError` (NOT a new domain class) carrying
  ``context["reason"] = "non_commercial_license"`` so the operator sees
  the licence stop-block at startup, not on first call (Spec 02 §10 #8
  fail-fast posture).
* **D-20-14 atomic generate().** Every call either returns a complete
  :class:`GenerationResult` from one branch or raises a domain error.
  Partial-progress streaming lives one layer up at the
  :class:`MultiModelImageBackend` (Spec 20 T16) — single-backend code
  emits clean domain errors so the T16 classifier (D-20-9) can decide
  fallback vs surface.
* **402 ``credits_expired``.** NVIDIA's RFC7807 body distinguishes
  credit exhaustion from other 402 cases; the backend maps it to
  :class:`ImageProviderError` with
  ``context["reason"] = "credits_expired"`` so the T16 classifier treats
  it as a FALLBACK trigger per D-20-9 — distinct from
  ``rate_limit`` / ``transient``.

References:
    docs/specs/phase2/spec_20/research.md R-20-3 (dual-branch surface);
    docs/specs/phase2/spec_20/decisions.md D-20-1 (launch model set),
    D-20-9 (T16 classifier fallback ladder), D-20-14 (atomic generate),
    D-20-X-flux-1-dev-license-block.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import TYPE_CHECKING, Any, NoReturn

import httpx
import openai

from persona.imagegen.errors import (
    ContentRejectedError,
    ImageGenUnavailableError,
    ImageProviderError,
)
from persona.imagegen.protocol import ImageBackend as _ImageBackendProtocol
from persona.imagegen.result import (
    GeneratedImage,
    GenerationResult,
    ImageGenOptions,
    ImageMediaType,
)
from persona.logging import get_logger

if TYPE_CHECKING:
    from persona.imagegen.config import ImageBackendConfig

__all__ = ["NvidiaImageBackend"]


_LOG = get_logger("imagegen.nvidia")


# ---------------------------------------------------------------------------
# Model dispatch tables (R-20-3, D-20-1)
# ---------------------------------------------------------------------------

#: Branch B (OpenAI-compat) — preferred path. Models served from
#: ``https://integrate.api.nvidia.com/v1/images/generations`` via the
#: openai SDK with custom ``base_url``.
_BRANCH_B_MODELS: frozenset[str] = frozenset(
    {
        "nvidia/flux.2-klein-4b",
        "nvidia/qwen-image",
        "nvidia/qwen-image-2512",
    }
)

#: Branch A (legacy GenAI) — commercial-clean SDXL path. Served from
#: ``https://ai.api.nvidia.com/v1/genai/{vendor}/{model}`` with the
#: NVIDIA-specific body shape.
_BRANCH_A_MODELS: frozenset[str] = frozenset(
    {
        "nvidia/stabilityai/stable-diffusion-xl",
    }
)

#: D-20-X-flux-1-dev-license-block. The hosted catalog exposes these
#: FLUX.1 variants but the upstream licence is non-commercial only. The
#: backend refuses to instantiate against them so operators see the
#: stop-block at startup.
_LICENCE_BLOCKED_MODELS: frozenset[str] = frozenset(
    {
        "nvidia/black-forest-labs/flux.1-dev",
        "nvidia/black-forest-labs/flux.1-kontext-dev",
    }
)


# Default endpoints. Branch B base_url is overridable via
# ``ImageBackendConfig.base_url`` (proxy / mock-server); Branch A is
# hard-coded because no operator-facing override is required at v0.1.
_BRANCH_A_BASE_URL = "https://ai.api.nvidia.com"
_BRANCH_B_BASE_URL = "https://integrate.api.nvidia.com/v1/"


# Neutral preset → (width, height) — Branch A accepts arbitrary dims
# similar to fal; Branch B normalises through the openai SDK.
_SIZE_DIMENSIONS: dict[str, tuple[int, int]] = {
    "1024x1024": (1024, 1024),
    "1024x1792": (1024, 1792),
    "1792x1024": (1792, 1024),
}


def _parse_size(size: str) -> tuple[int, int]:
    """Parse ``"WxH"`` into ``(width, height)``."""
    width_str, _, height_str = size.partition("x")
    return int(width_str), int(height_str)


def _branch_a_endpoint(model: str) -> str:
    """Build the Branch A URL for ``model``.

    The hosted catalog id is ``nvidia/{vendor}/{family}``; the GenAI
    endpoint expects ``/v1/genai/{vendor}/{family}`` so we strip the
    leading ``nvidia/`` prefix.
    """
    vendor_model = model.removeprefix("nvidia/")
    return f"{_BRANCH_A_BASE_URL}/v1/genai/{vendor_model}"


class NvidiaImageBackend:
    """Async image-generation backend for the NVIDIA Build Catalog.

    Implements :class:`persona.imagegen.protocol.ImageBackend`. Dispatches
    Branch B (OpenAI-compat) for the FLUX.2-klein / Qwen-Image families
    and Branch A (legacy GenAI) for the commercial-clean SDXL path.

    Constructor fail-fast (Spec 02 D-02-* construction-time-fail-fast):

    * Missing / empty ``api_key`` →
      :class:`ImageGenUnavailableError(reason="missing_api_key")`.
    * D-20-X-flux-1-dev-license-block model →
      :class:`ImageProviderError(reason="non_commercial_license")`.
    * Unknown model (not in either branch's allowed set) →
      :class:`ImageProviderError(reason="unsupported_model")`.
    """

    def __init__(self, config: ImageBackendConfig) -> None:
        """Construct + validate the backend.

        Args:
            config: Image backend configuration. ``config.provider`` MUST
                be ``"nvidia"`` (the factory enforces this);
                ``config.model`` must be in :data:`_BRANCH_A_MODELS` or
                :data:`_BRANCH_B_MODELS` — D-20-X-flux-1-dev-license-block
                models are rejected unconditionally.

        Raises:
            ImageGenUnavailableError: ``config.api_key`` is ``None`` /
                empty.
            ImageProviderError: provider mismatch, licence-blocked model,
                or unknown model.
        """
        if config.provider != "nvidia":
            msg = (
                f"NvidiaImageBackend does not handle provider {config.provider!r}; "
                "use load_image_backend() to dispatch."
            )
            raise ImageProviderError(msg, context={"provider": str(config.provider)})

        if config.api_key is None or not config.api_key.get_secret_value():
            raise ImageGenUnavailableError(
                "missing NVIDIA API key",
                context={"provider": "nvidia", "reason": "missing_api_key"},
            )

        model = config.model

        # D-20-X-flux-1-dev-license-block (mandatory guard). FLUX.1-dev
        # and FLUX.1-kontext-dev are listed on the NVIDIA hosted catalog
        # but carry a non-commercial upstream licence; refuse at
        # construction so the operator sees the stop-block at startup,
        # not on first call. ImageProviderError (NOT a new domain class)
        # carries the reason discriminator.
        if model in _LICENCE_BLOCKED_MODELS:
            raise ImageProviderError(
                f"model {model!r} is non-commercial only and refused by NvidiaImageBackend",
                context={
                    "provider": "nvidia",
                    "model": model,
                    "reason": "non_commercial_license",
                    "hint": (
                        "use nvidia/flux.2-klein-4b instead (only FLUX variant "
                        "commercial-clean on hosted catalog); SDXL via legacy "
                        "GenAI is alternative commercial-clean option"
                    ),
                },
            )

        if model in _BRANCH_B_MODELS:
            self._branch: str = "B"
        elif model in _BRANCH_A_MODELS:
            self._branch = "A"
        else:
            supported = sorted(_BRANCH_A_MODELS | _BRANCH_B_MODELS)
            raise ImageProviderError(
                f"unknown NVIDIA model {model!r}",
                context={
                    "provider": "nvidia",
                    "model": model,
                    "reason": "unsupported_model",
                    "supported": ", ".join(supported),
                },
            )

        self._config = config
        self._model = model
        self._timeout = config.request_timeout_s
        self._api_key = config.api_key.get_secret_value()
        self._base_url_b = config.base_url or _BRANCH_B_BASE_URL

        # Branch B uses the openai SDK with a custom base URL — only
        # instantiated for Branch B models so Branch A operators do not
        # pay the construction cost. Branch A uses a fresh
        # ``httpx.AsyncClient`` per call (NVCF poll loop reuses it).
        self._openai_client: openai.AsyncOpenAI | None = None
        if self._branch == "B":
            self._openai_client = openai.AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url_b,
                timeout=self._timeout,
            )

        _LOG.debug(
            "constructed",
            provider="nvidia",
            model=self._model,
            branch=self._branch,
            timeout_s=self._timeout,
        )

    @property
    def provider_name(self) -> str:
        """Return the stable provider identifier ``"nvidia"``."""
        return "nvidia"

    @property
    def model_name(self) -> str:
        """Return the configured NVIDIA model identifier."""
        return self._model

    async def generate(
        self,
        prompt: str,
        *,
        options: ImageGenOptions | None = None,
    ) -> GenerationResult:
        """Single-shot image generation against NVIDIA.

        Atomic per D-20-14: returns a complete :class:`GenerationResult`
        from one branch OR raises a domain error. No partial streaming.

        Args:
            prompt: Merged text prompt (visual_style merging happens
                upstream in T11 ``_merge.py``).
            options: Neutral generation knobs. ``None`` means the default
                :class:`ImageGenOptions`.

        Returns:
            :class:`GenerationResult` with one image per requested count.

        Raises:
            ImageGenUnavailableError: NVIDIA rejected the API key
                (401/403).
            ImageProviderError: rate limit (``reason="rate_limit"``),
                credits expired (``reason="credits_expired"`` — D-20-9
                fallback trigger), transient 5xx
                (``reason="transient"``), timeout
                (``reason="timeout"``).
            ContentRejectedError: provider moderation refused the prompt
                (``reason="provider_moderation"``).
        """
        opts = options or ImageGenOptions()
        started = time.perf_counter()

        if self._branch == "B":
            images = await self._dispatch_openai_compat(prompt, opts)
        else:
            images = await self._dispatch_legacy_genai(prompt, opts)

        latency_ms = (time.perf_counter() - started) * 1000.0
        return GenerationResult(
            images=images,
            provider="nvidia",
            model=self._model,
            latency_ms=latency_ms,
        )

    async def edit(
        self,
        input_image: GeneratedImage,
        instructions: str,
        *,
        options: ImageGenOptions | None = None,
    ) -> GenerationResult:
        """Reserved for v1.x — delegates to the Protocol default."""
        return await _ImageBackendProtocol.edit(self, input_image, instructions, options=options)

    # ------------------------------------------------------------------
    # Branch B — OpenAI-compat
    # ------------------------------------------------------------------

    async def _dispatch_openai_compat(
        self,
        prompt: str,
        opts: ImageGenOptions,
    ) -> list[GeneratedImage]:
        """Branch B dispatch through the openai SDK against NVIDIA's
        OpenAI-compat endpoint. Returns parsed images; the caller wraps
        with provenance + latency.
        """
        assert self._openai_client is not None  # Branch B always allocates it
        width, height = _SIZE_DIMENSIONS.get(opts.size, _parse_size(opts.size))
        kwargs: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "size": f"{width}x{height}",
            "n": opts.count,
        }

        try:
            response = await self._openai_client.images.generate(**kwargs)
        except Exception as exc:  # noqa: BLE001 — adapter boundary
            self._reraise_openai(exc)

        data = getattr(response, "data", None) or []
        if not data:
            raise ImageProviderError(
                "nvidia (branch B) returned an empty data array",
                context={"provider": "nvidia", "model": self._model, "reason": "transient"},
            )

        results: list[GeneratedImage] = []
        for entry in data:
            b64 = getattr(entry, "b64_json", None) or ""
            if not b64:
                raise ImageProviderError(
                    "nvidia (branch B) response entry missing b64_json",
                    context={
                        "provider": "nvidia",
                        "model": self._model,
                        "reason": "transient",
                    },
                )
            try:
                image_bytes = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError) as exc:
                raise ImageProviderError(
                    "nvidia (branch B) returned malformed base64 image data",
                    context={
                        "provider": "nvidia",
                        "model": self._model,
                        "reason": "transient",
                    },
                ) from exc
            results.append(
                GeneratedImage(
                    image_bytes=image_bytes,
                    media_type="image/png",
                    width=width,
                    height=height,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Branch A — Legacy GenAI (NVCF poll)
    # ------------------------------------------------------------------

    async def _dispatch_legacy_genai(
        self,
        prompt: str,
        opts: ImageGenOptions,
    ) -> list[GeneratedImage]:
        """Branch A dispatch against ``ai.api.nvidia.com/v1/genai/...``.

        Builds the NVIDIA-specific body, posts it, handles the NVCF 202
        + ``NVCF-REQID`` poll loop, parses the ``artifacts[].base64``
        response. Returns parsed images.
        """
        width, height = _SIZE_DIMENSIONS.get(opts.size, _parse_size(opts.size))
        endpoint = _branch_a_endpoint(self._model)
        body: dict[str, Any] = {
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "cfg_scale": 5,
            "sampler": "K_DPMPP_2M",
            "steps": 25,
            "seed": 0,
            "samples": opts.count,
            "height": height,
            "width": width,
            "mode": "text-to-image",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(endpoint, json=body, headers=headers)
                response = await self._poll_nvcf(client, response, headers)
                self._raise_for_status(response)
                payload = response.json()
        except (ImageGenUnavailableError, ImageProviderError, ContentRejectedError):
            raise
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "nvidia (branch A) request timed out",
                context={"provider": "nvidia", "model": self._model, "reason": "timeout"},
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageProviderError(
                "nvidia (branch A) request failed",
                context={"provider": "nvidia", "model": self._model, "reason": "transient"},
            ) from exc

        return self._parse_artifacts(payload, width, height)

    async def _poll_nvcf(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response,
        headers: dict[str, str],
    ) -> httpx.Response:
        """Poll the NVCF status endpoint while the response is 202.

        Returns the terminal response (status != 202). The poll interval
        defaults to 1.0s when ``NVCF-POLL-SECONDS`` is absent; the loop
        cap is :attr:`self._timeout` total wall-clock so a misbehaving
        function does not stall the caller indefinitely.
        """
        deadline = time.perf_counter() + self._timeout
        while response.status_code == 202:
            req_id = response.headers.get("NVCF-REQID")
            if not req_id:
                # 202 without a reqId is non-standard; surface as
                # transient so the T16 classifier can decide.
                raise ImageProviderError(
                    "nvidia (branch A) 202 without NVCF-REQID header",
                    context={
                        "provider": "nvidia",
                        "model": self._model,
                        "reason": "transient",
                    },
                )
            poll_seconds_raw = response.headers.get("NVCF-POLL-SECONDS", "1")
            try:
                poll_seconds = float(poll_seconds_raw)
            except (TypeError, ValueError):
                poll_seconds = 1.0
            await asyncio.sleep(max(0.0, poll_seconds))
            if time.perf_counter() > deadline:
                raise ImageProviderError(
                    "nvidia (branch A) NVCF poll exceeded request_timeout_s",
                    context={
                        "provider": "nvidia",
                        "model": self._model,
                        "reason": "timeout",
                    },
                )
            status_url = f"{_BRANCH_A_BASE_URL}/v2/nvcf/pexec/status/{req_id}"
            response = await client.get(status_url, headers=headers)
        return response

    def _parse_artifacts(
        self,
        payload: Any,  # noqa: ANN401 — JSON body
        width: int,
        height: int,
    ) -> list[GeneratedImage]:
        """Decode ``artifacts[].base64`` into :class:`GeneratedImage`.

        Branch A's response uses the literal field name ``base64`` (NOT
        ``b64_json``). Empty artifact arrays or missing ``base64`` keys
        surface as ``transient`` so the T16 classifier can decide.
        """
        if not isinstance(payload, dict):
            raise ImageProviderError(
                "nvidia (branch A) response is not a JSON object",
                context={"provider": "nvidia", "model": self._model, "reason": "transient"},
            )
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ImageProviderError(
                "nvidia (branch A) returned no artifacts",
                context={"provider": "nvidia", "model": self._model, "reason": "transient"},
            )

        results: list[GeneratedImage] = []
        for entry in artifacts:
            if not isinstance(entry, dict):
                raise ImageProviderError(
                    "nvidia (branch A) artifact entry is not a dict",
                    context={
                        "provider": "nvidia",
                        "model": self._model,
                        "reason": "transient",
                    },
                )
            b64 = entry.get("base64")
            if not isinstance(b64, str) or not b64:
                raise ImageProviderError(
                    "nvidia (branch A) artifact missing base64",
                    context={
                        "provider": "nvidia",
                        "model": self._model,
                        "reason": "transient",
                    },
                )
            try:
                image_bytes = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError) as exc:
                raise ImageProviderError(
                    "nvidia (branch A) malformed base64 image data",
                    context={
                        "provider": "nvidia",
                        "model": self._model,
                        "reason": "transient",
                    },
                ) from exc
            media_type: ImageMediaType = "image/png"
            results.append(
                GeneratedImage(
                    image_bytes=image_bytes,
                    media_type=media_type,
                    width=width,
                    height=height,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Error mapping
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map a Branch A ``httpx.Response`` to a domain exception.

        Distinguishes the four cases the T16 classifier (D-20-9) needs:

        * 401/403 → :class:`ImageGenUnavailableError(reason="auth")`.
        * 402 with RFC7807 ``"credits expired"`` body →
          :class:`ImageProviderError(reason="credits_expired")` so T16
          routes to the next provider rather than retrying the same
          key.
        * 422 → :class:`ContentRejectedError(reason="provider_moderation",
          stage="input")`.
        * 429 → :class:`ImageProviderError(reason="rate_limit")` with
          ``retry_after_s`` when the header is present.
        * 5xx → :class:`ImageProviderError(reason="transient")`.
        """
        status = response.status_code
        if status < 400:
            return
        if status in {401, 403}:
            raise ImageGenUnavailableError(
                "nvidia rejected the API key",
                context={
                    "provider": "nvidia",
                    "model": self._model,
                    "reason": "auth",
                    "status": str(status),
                },
            )
        if status == 402:
            # RFC7807 distinguishes "credits expired" from other 402
            # variants; the T16 classifier (D-20-9) treats this as a
            # FALLBACK trigger so the next provider in the chain gets
            # tried rather than the user seeing a hard 402.
            reason = "transient"
            try:
                body = response.json()
            except (ValueError, TypeError):
                body = None
            if isinstance(body, dict):
                title = str(body.get("title", "")).lower()
                detail = str(body.get("detail", "")).lower()
                if "credit" in title or "credit" in detail:
                    reason = "credits_expired"
            raise ImageProviderError(
                "nvidia returned 402",
                context={
                    "provider": "nvidia",
                    "model": self._model,
                    "reason": reason,
                    "status": "402",
                },
            )
        if status == 422:
            raise ContentRejectedError(
                "nvidia rejected the prompt under content policy",
                context={
                    "provider": "nvidia",
                    "model": self._model,
                    "reason": "provider_moderation",
                    "stage": "input",
                },
            )
        if status == 429:
            retry_after = response.headers.get("retry-after")
            ctx: dict[str, str] = {
                "provider": "nvidia",
                "model": self._model,
                "reason": "rate_limit",
            }
            if retry_after is not None:
                ctx["retry_after_s"] = str(retry_after)
            raise ImageProviderError("nvidia rate limited", context=ctx)
        if 500 <= status < 600:
            raise ImageProviderError(
                "nvidia upstream 5xx",
                context={
                    "provider": "nvidia",
                    "model": self._model,
                    "reason": "transient",
                    "status": str(status),
                },
            )
        raise ImageProviderError(
            "nvidia upstream error",
            context={
                "provider": "nvidia",
                "model": self._model,
                "reason": "transient",
                "status": str(status),
            },
        )

    def _reraise_openai(self, exc: BaseException) -> NoReturn:
        """Map an openai SDK exception (Branch B) into the domain hierarchy.

        Mirrors :meth:`persona.imagegen.openai_image.OpenAIImageBackend._reraise`
        with NVIDIA's additional ``credits_expired`` discriminator on the
        402 path (the openai SDK surfaces 402 as a generic
        ``BadRequestError`` or ``APIStatusError``; we inspect the body).
        """
        provider = "nvidia"
        model = self._model

        if isinstance(exc, openai.AuthenticationError):
            raise ImageGenUnavailableError(
                str(exc),
                context={"provider": provider, "model": model, "reason": "auth"},
            ) from exc

        if isinstance(exc, openai.RateLimitError):
            retry_after = _extract_retry_after_s(
                getattr(getattr(exc, "response", None), "headers", None)
            )
            ctx: dict[str, str] = {"provider": provider, "model": model, "reason": "rate_limit"}
            if retry_after is not None:
                ctx["retry_after_s"] = retry_after
            raise ImageProviderError(str(exc), context=ctx) from exc

        if isinstance(exc, openai.NotFoundError):
            raise ImageProviderError(
                str(exc),
                context={
                    "provider": provider,
                    "model": model,
                    "reason": "model_not_found",
                },
            ) from exc

        if isinstance(exc, openai.APIStatusError):
            status = getattr(exc, "status_code", 0)
            if status == 402:
                reason = "transient"
                body = getattr(exc, "body", None)
                if isinstance(body, dict):
                    title = str(body.get("title", "")).lower()
                    detail = str(body.get("detail", "")).lower()
                    if "credit" in title or "credit" in detail:
                        reason = "credits_expired"
                raise ImageProviderError(
                    str(exc),
                    context={
                        "provider": provider,
                        "model": model,
                        "reason": reason,
                        "status": "402",
                    },
                ) from exc

        if isinstance(exc, openai.BadRequestError):
            raise ImageProviderError(
                str(exc),
                context={
                    "provider": provider,
                    "model": model,
                    "reason": "bad_request",
                },
            ) from exc

        if isinstance(exc, openai.APITimeoutError | openai.APIConnectionError):
            raise ImageProviderError(
                str(exc),
                context={"provider": provider, "model": model, "reason": "timeout"},
            ) from exc

        raise ImageProviderError(
            str(exc),
            context={
                "provider": provider,
                "model": model,
                "reason": "transient",
                "underlying": type(exc).__name__,
            },
        ) from exc


def _extract_retry_after_s(headers: Any) -> str | None:  # noqa: ANN401 — SDK type
    """Return the ``retry-after`` header as a string, or ``None``."""
    if headers is None:
        return None
    try:
        value = headers.get("retry-after") if hasattr(headers, "get") else None
    except (AttributeError, TypeError):
        return None
    if value is None:
        return None
    return str(value)
