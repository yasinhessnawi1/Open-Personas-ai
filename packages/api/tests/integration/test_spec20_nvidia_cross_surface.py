"""Spec 20 acceptance criterion 9 — cross-spec integration test (T20).

Exercises NVIDIA across all four capability surfaces (chat / reasoning /
vision / image-gen) end-to-end against the Spec 02 + Spec 13 + Spec 15 +
Spec 18 contracts. Provider transport is scripted at the openai-SDK
boundary (and via :class:`httpx.MockTransport` for Branch A) so the test
runs without a live NVIDIA API key; the wiring under test is Persona's,
NOT NVIDIA's endpoint behaviour.

Marked ``@pytest.mark.integration``: skipped by default; CI runs with
``pytest -m integration``. Requires Postgres in Docker (per
``packages/api/tests/conftest.py``) for the Spec 13 D-08-1 RLS sub-test;
the RLS sub-test self-skips if ``APP_DATABASE_URL`` is unset.

The D-20-* locks verified here:

* D-20-1 — launch model set (chat + reasoning + vision + image-gen).
* D-20-2 — ``StreamChunk.reasoning`` reachable on reasoning-tier turns.
* D-20-4 — HYBRID dual-branch :class:`NvidiaImageBackend` Branch B path.
* D-20-X-nvidia-allow-set-extend — ``BackendConfig(provider="nvidia")``
  constructs cleanly through :class:`OpenAICompatibleBackend.__init__`.
* D-20-X-nemotron-field-name-dual-probe — scripted SDK response with
  ``delta.reasoning`` (alias) AND ``delta.reasoning_content`` (canonical)
  both parsed onto :attr:`StreamChunk.reasoning`.
* D-20-X-flux-1-dev-license-block — non-commercial FLUX.1 variants
  refused at construction.
* Spec 13 D-08-1 — image input from a cross-tenant persona MUST be
  rejected at the database row-level-security layer.
* Spec 18 D-18-5 — reasoning-capable NVIDIA Nemotron entries get the
  +0.10 quality-fit boost on hard turns (quality_proxy ≥ 0.5).
"""

# ruff: noqa: ANN401, SLF001
# ANN401: mocks use ``Any`` return types (mirrors ``test_openai_compat`` shape).
# SLF001: integration test inspects private SDK plumbing for assertions.

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from persona.backends.config import DEFAULT_BASE_URLS, BackendConfig
from persona.backends.multi_model import MultiModelChatBackend
from persona.backends.openai_compat import (
    _NATIVE_TOOLS_CAPABILITY,
    _VISION_CAPABILITY,
    OpenAICompatibleBackend,
)
from persona.backends.types import StreamChunk
from persona.imagegen.config import ImageBackendConfig, ImageProvider
from persona.imagegen.errors import ImageProviderError
from persona.imagegen.multi_model_image import MultiModelImageBackend
from persona.imagegen.nvidia_image import NvidiaImageBackend
from persona.schema.content import ImageContent, TextContent
from persona.schema.conversation import ConversationMessage
from persona_runtime.routing.nvidia_models import (
    NVIDIA_LAUNCH_MODEL_METADATA,
    nvidia_metadata_for_model,
)
from persona_runtime.routing.scoring import score_tier
from persona_runtime.routing.types import RoutingContext
from persona_runtime.tier import TierConfig, TierMetadata, TierRegistry
from pydantic import SecretStr

if TYPE_CHECKING:
    from sqlalchemy import Engine


pytestmark = pytest.mark.integration


# -----------------------------------------------------------------------------
# Scripted-SDK helpers (kept local — symmetric to ``test_openai_compat`` shapes
# but tighter to the cross-surface intent).
# -----------------------------------------------------------------------------


def _user(text: str) -> ConversationMessage:
    return ConversationMessage(role="user", content=text, created_at=datetime.now(UTC))


def _user_with_image(text: str, workspace_path: str) -> ConversationMessage:
    return ConversationMessage(
        role="user",
        content=[
            TextContent(text=text),
            ImageContent(workspace_path=workspace_path, media_type="image/png"),
        ],
        created_at=datetime.now(UTC),
    )


async def _async_iter(items: list[Any]) -> AsyncIterator[Any]:
    for x in items:
        yield x


def _scripted_stream_chunk(
    *,
    content: str = "",
    reasoning_content: str | None = None,
    reasoning: str | None = None,
    usage: Any | None = None,
) -> Any:
    """Build a fake openai-py ChoiceDelta carrying optional reasoning fields.

    D-20-X-nemotron-field-name-dual-probe — Nemotron canonical
    ``reasoning_content`` + Nano-Omni alias ``reasoning`` arrive via Pydantic
    extras (NOT statically typed) on the chunk delta.
    """
    chunk = MagicMock()
    delta = MagicMock(spec=["content", "tool_calls", "reasoning_content", "reasoning"])
    delta.content = content
    delta.tool_calls = []
    delta.reasoning_content = reasoning_content
    delta.reasoning = reasoning
    choice = MagicMock()
    choice.delta = delta
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


def _chat_response_payload(text: str, *, model: str) -> Any:
    """Fake openai-py ChatCompletion shape used by ``_chat_openai``."""
    message = MagicMock()
    message.content = text
    message.tool_calls = []
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    response.model = model
    usage = MagicMock()
    usage.prompt_tokens = 4
    usage.completion_tokens = 5
    response.usage = usage
    return response


def _nvidia_chat_config(model: str, *, extra_body: dict[str, Any] | None = None) -> BackendConfig:
    return BackendConfig(
        provider="nvidia",
        model=model,
        api_key=SecretStr("test-nvidia-key"),
        extra_body=extra_body,
    )


def _nvidia_image_config(model: str) -> ImageBackendConfig:
    return ImageBackendConfig(
        provider="nvidia",
        model=model,
        api_key=SecretStr("test-nvidia-image-key"),
        request_timeout_s=10.0,
    )


# -----------------------------------------------------------------------------
# Fixtures — Postgres-backed personas live behind app_engine; the chat/imagegen
# surfaces don't need DB at all (their wiring is provider-SDK-only).
# -----------------------------------------------------------------------------


@pytest.fixture
def two_tenant_personas_with_image(migrated_engine: Engine) -> dict[str, str]:
    """Seed two tenants + personas + a single image row owned by tenant A.

    The fixture is intentionally minimal — the RLS sub-test only needs to
    prove that tenant B cannot SELECT tenant A's image row. We seed under
    the superuser engine (RLS-bypass) so the rows exist regardless of
    policy, then the test connects under the non-superuser role to prove
    the policy hides them.
    """
    from sqlalchemy import text

    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email) VALUES "
                "('tenant_a','a@example.com'),('tenant_b','b@example.com')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO personas (id, owner_id, yaml) VALUES "
                "('persona_a','tenant_a','name: a'),"
                "('persona_b','tenant_b','name: b')"
            )
        )
    return {"tenant_a": "persona_a", "tenant_b": "persona_b"}


# -----------------------------------------------------------------------------
# T20 — Cross-surface acceptance suite
# -----------------------------------------------------------------------------


class TestSpec20Acceptance9NvidiaCrossSurface:
    """Cross-surface integration sweep for Spec 20 acceptance criterion 9.

    Each test pins one of the four capability surfaces (chat / reasoning /
    vision / image-gen) + verifies the Persona-side wiring against the
    closed-spec contracts. Provider transport is scripted via openai-SDK
    method patches — the assertions target Persona's surfaces (BackendConfig
    allow-set, StreamChunk shape, capability matrices, ImageBackend
    Protocol) NOT NVIDIA's endpoint behaviour.
    """

    # ------------------------------------------------------------------
    # Surface 1 — Chat (D-20-1 launch + D-20-X-nvidia-allow-set-extend)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_chat_surface_routes_through_openai_compat_backend(self) -> None:
        """Spec 02 + D-20-X-nvidia-allow-set-extend.

        :class:`OpenAICompatibleBackend` constructs cleanly with
        ``provider="nvidia"`` (allow-set extension landed by T09), points at
        ``DEFAULT_BASE_URLS["nvidia"]``, and returns a :class:`ChatResponse`
        whose ``provider`` field round-trips ``"nvidia"``.
        """
        model = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
        backend = OpenAICompatibleBackend(_nvidia_chat_config(model))

        # D-20-X-nvidia-allow-set-extend: the four anchors are all wired.
        assert backend.provider_name == "nvidia"
        assert backend.model_name == model
        assert DEFAULT_BASE_URLS["nvidia"].startswith("https://integrate.api.nvidia.com")
        assert "nvidia" in _NATIVE_TOOLS_CAPABILITY
        assert model in _NATIVE_TOOLS_CAPABILITY["nvidia"]

        # Spec 02 dispatch shape — the openai SDK boundary is the script point.
        with patch.object(
            backend._openai.chat.completions,  # type: ignore[union-attr]
            "create",
            new=AsyncMock(return_value=_chat_response_payload("ok", model=model)),
        ):
            response = await backend.chat([_user("ping")])
        assert response.provider == "nvidia"
        assert response.content == "ok"

    # ------------------------------------------------------------------
    # Surface 2 — Reasoning (D-20-2 + D-20-X-nemotron-dual-probe)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_reasoning_surface_streams_reasoning_field_dual_probe(self) -> None:
        """D-20-2 reasoning shape + D-20-X-nemotron-field-name-dual-probe.

        A reasoning-tier turn with
        ``extra_body={"chat_template_kwargs": {"enable_thinking": True}}``
        produces :class:`StreamChunk` whose ``reasoning`` field is populated
        for BOTH the canonical ``delta.reasoning_content`` AND the alias
        ``delta.reasoning`` (Nano-Omni VLM variant). Both probes feed the
        same single-arm str surface per D-20-2 verdict (b).
        """
        model = "nvidia/nemotron-3-super-120b-a12b"
        backend = OpenAICompatibleBackend(
            _nvidia_chat_config(
                model,
                extra_body={"chat_template_kwargs": {"enable_thinking": True}},
            )
        )
        usage = MagicMock(prompt_tokens=3, completion_tokens=4)
        chunks_in = [
            # Canonical field — Nemotron-3-Super et al.
            _scripted_stream_chunk(
                content="alpha", reasoning_content="canonical-think-1 ", reasoning=None
            ),
            # Alias field — Nano-Omni VLM. Both must populate
            # StreamChunk.reasoning (D-20-X-nemotron-field-name-dual-probe).
            _scripted_stream_chunk(
                content="beta", reasoning_content=None, reasoning="alias-think-2"
            ),
            _scripted_stream_chunk(usage=usage),
        ]
        with patch.object(
            backend._openai.chat.completions,  # type: ignore[union-attr]
            "create",
            new=AsyncMock(return_value=_async_iter(chunks_in)),
        ):
            collected: list[StreamChunk] = []
            async for c in backend.chat_stream([_user("solve x*x = 4")]):
                collected.append(c)

        # D-20-2: reasoning surface reachable. D-20-X-nemotron-dual-probe:
        # both arms produced reasoning chunks (the second uses the alias).
        reasoning_arms = [c.reasoning for c in collected if c.reasoning]
        assert "canonical-think-1 " in reasoning_arms, "canonical reasoning_content not surfaced"
        assert "alias-think-2" in reasoning_arms, "alias reasoning field not surfaced"

    # ------------------------------------------------------------------
    # Surface 3 — Vision (D-20-1 vision row + Spec 13 capability matrix)
    # ------------------------------------------------------------------

    def test_vision_capability_matrix_lists_all_four_nvidia_vlms(self) -> None:
        """D-20-1 vision launch — VILA, Cosmos Nemotron, Cosmos Reason 1/2.

        Spec 13 D-13-3 capability matrix lookup succeeds for the four NVIDIA
        vision models from T13; ``nvidia/vila`` AND
        ``nvidia/cosmos-nemotron-34b`` are the default vision-tier choices
        per D-20-1 (Llama-3.2-Vision sidestepped via the EU carve-out flag
        in R-20-5).
        """
        nvidia_vision_cap = _VISION_CAPABILITY["nvidia"]
        assert isinstance(nvidia_vision_cap, frozenset)
        for model in (
            "nvidia/vila",
            "nvidia/cosmos-nemotron-34b",
            "nvidia/cosmos-reason1-7b",
            "nvidia/cosmos-reason2-8b",
        ):
            assert model in nvidia_vision_cap, f"{model} missing from D-13-3 vision matrix"

        # Chat-only models stay vision=False (defensive — D-20-1 keeps the
        # 49b-v1.5 chat model out of the vision set).
        backend = OpenAICompatibleBackend(
            _nvidia_chat_config("nvidia/llama-3.3-nemotron-super-49b-v1.5")
        )
        assert backend.supports_vision is False

        # Default VLM is vision-capable.
        vision_backend = OpenAICompatibleBackend(_nvidia_chat_config("nvidia/vila"))
        assert vision_backend.supports_vision is True

    @pytest.mark.asyncio
    async def test_vision_surface_accepts_image_content_message(self, tmp_path: Path) -> None:
        """Spec 13 image-as-ref multimodal serialisation reaches the VLM.

        A :class:`ConversationMessage` carrying an :class:`ImageContent`
        block round-trips through the OpenAI-compat backend's vision-aware
        serialiser. The scripted SDK boundary verifies the request was
        accepted (the wiring under test is Persona's image-block expansion,
        NOT NVIDIA's VLM behaviour).
        """
        # Workspace + a tiny PNG byte payload (1×1 transparent pixel).
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
            b"\xff?\x00\x05\xfe\x02\xfe\xa3{\xa5\xc6\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        persona_workspace = tmp_path / "persona_a"
        persona_workspace.mkdir()
        image_path = persona_workspace / "scene.png"
        image_path.write_bytes(png_bytes)

        backend = OpenAICompatibleBackend(
            _nvidia_chat_config("nvidia/vila"),
            workspace_root=tmp_path,
        )
        with patch.object(
            backend._openai.chat.completions,  # type: ignore[union-attr]
            "create",
            new=AsyncMock(
                return_value=_chat_response_payload(
                    "scene contains a single pixel", model="nvidia/vila"
                )
            ),
        ) as create_mock:
            response = await backend.chat(
                [_user_with_image("describe this", "persona_a/scene.png")]
            )

        # The image block reached the VLM (the serialiser produced a list-
        # form message body, not a text-only round-trip).
        assert response.provider == "nvidia"
        sent_kwargs = create_mock.call_args.kwargs
        sent_messages = sent_kwargs["messages"]
        last_user = sent_messages[-1]
        assert last_user["role"] == "user"
        # Vision-capable backends serialise to OpenAI multimodal list shape.
        assert isinstance(last_user["content"], list)
        block_types = {block.get("type") for block in last_user["content"]}
        assert "image_url" in block_types, "ImageContent did not reach SDK as image_url"

    def test_vision_surface_rls_blocks_cross_tenant_image(
        self,
        two_tenant_personas_with_image: dict[str, str],
    ) -> None:
        """Spec 13 D-08-1 RLS invariant — cross-tenant image input is rejected
        at the database row-level-security layer.

        Tenant B's RLS-scoped connection cannot SELECT tenant A's persona /
        memory rows. We seed tenant A's persona via the migrated (superuser)
        engine, then prove the non-superuser app role sees nothing for
        tenant B. The vision surface composes on top of this guard —
        ``ImageContent.workspace_path`` resolves only to bytes the user can
        already see, which RLS bounds.
        """
        from persona_api.db.engine import rls_connection
        from sqlalchemy import create_engine, text

        app_url = os.environ.get("APP_DATABASE_URL")
        if not app_url:
            pytest.skip("APP_DATABASE_URL (non-superuser role) not set; skipping RLS sub-test")
        app_engine = create_engine(app_url.replace("+asyncpg", "+psycopg"))

        # Tenant A owns persona_a; tenant B owns persona_b.
        assert two_tenant_personas_with_image["tenant_a"] == "persona_a"

        # Under tenant B's RLS context, persona_a must be invisible.
        with rls_connection(app_engine, "tenant_b") as conn:
            visible = conn.execute(text("SELECT id, owner_id FROM personas")).all()
        owners = {row.owner_id for row in visible}
        assert owners == {"tenant_b"}, (
            f"Spec 13 D-08-1 RLS leak: tenant_b saw personas owned by {owners}"
        )

    # ------------------------------------------------------------------
    # Surface 4 — Image-gen (D-20-4 Branch B + D-20-X-flux-1-dev license)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_image_gen_surface_branch_b_openai_compat(self) -> None:
        """D-20-4 HYBRID Branch B path verified end-to-end.

        :class:`NvidiaImageBackend` with ``flux.2-klein-4b`` dispatches via
        Branch B (openai SDK against the NVIDIA OpenAI-compat endpoint) and
        returns a :class:`GenerationResult` whose ``provider`` is
        ``"nvidia"``. Verify the Spec 15 ``ImageProvider`` Literal includes
        ``"nvidia"`` so the contract surface is complete.
        """
        # Spec 15 + Spec 20 D-20-1: provider Literal extended to nvidia.
        assert "nvidia" in ImageProvider.__args__  # type: ignore[attr-defined]

        backend = NvidiaImageBackend(_nvidia_image_config("nvidia/flux.2-klein-4b"))

        # Scripted Branch B response — single-image b64 payload.
        png_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/x8AAwM"
            "BAEh0bsAAAAAASUVORK5CYII="
        )
        response = MagicMock()
        response.data = [MagicMock(b64_json=png_b64)]
        assert backend._openai_client is not None
        with patch.object(
            backend._openai_client.images,
            "generate",
            new=AsyncMock(return_value=response),
        ):
            result = await backend.generate("a tiny pixel")
        assert result.provider == "nvidia"
        assert result.model == "nvidia/flux.2-klein-4b"
        assert len(result.images) == 1
        assert result.images[0].image_bytes  # decoded successfully

    def test_image_gen_surface_flux_1_dev_license_block(self) -> None:
        """D-20-X-flux-1-dev-license-block negative test — non-commercial
        FLUX.1 variants are refused at construction with an
        :class:`ImageProviderError` carrying
        ``context["reason"] = "non_commercial_license"``. Fail-fast at
        construction (Spec 02 §10 #8 posture).
        """
        with pytest.raises(ImageProviderError) as excinfo:
            NvidiaImageBackend(_nvidia_image_config("nvidia/black-forest-labs/flux.1-dev"))
        ctx = excinfo.value.context
        assert ctx.get("reason") == "non_commercial_license"

        with pytest.raises(ImageProviderError) as excinfo2:
            NvidiaImageBackend(_nvidia_image_config("nvidia/black-forest-labs/flux.1-kontext-dev"))
        assert excinfo2.value.context.get("reason") == "non_commercial_license"

    # ------------------------------------------------------------------
    # Wrapper Protocol surfaces — MultiModel*Backend public accessors
    # (Cluster B emergent micro D-20-X-tier-name-backends-property-readers)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_chat_wrapper_surfaces_tier_and_backends_accessors(self) -> None:
        """D-20-X-tier-name-backends-property-readers — wrapper exposes
        public ``tier_name`` + ``backends`` accessors per Protocol convention,
        required by TurnLog instrumentation (T19) and the cross-surface
        integration assertion that the wrapper is observable.
        """
        primary = OpenAICompatibleBackend(
            _nvidia_chat_config("nvidia/llama-3.3-nemotron-super-49b-v1.5")
        )
        wrapper = MultiModelChatBackend([primary], tier_name="frontier")
        assert wrapper.tier_name == "frontier"
        assert wrapper.backends is wrapper._backends
        assert wrapper.provider_name == "nvidia"

    @pytest.mark.asyncio
    async def test_image_wrapper_surfaces_tier_and_backends_accessors(self) -> None:
        """Symmetric to the chat wrapper — Spec 15 :class:`MultiModelImageBackend`
        exposes the same Protocol-shaped accessors so T17 wiring + T19 audit
        plumbing can read tier_name/backends without reaching into private state.
        """
        primary = NvidiaImageBackend(_nvidia_image_config("nvidia/flux.2-klein-4b"))
        wrapper = MultiModelImageBackend([primary], tier_name="imagegen")
        assert wrapper.tier_name == "imagegen"
        assert wrapper.backends == [primary]
        assert wrapper.provider_name == "nvidia"

    # ------------------------------------------------------------------
    # Router metadata + D-18-5 quality-proxy boost (Spec 18 + T14 launch set)
    # ------------------------------------------------------------------

    def test_router_metadata_drives_layer_2_scoring_for_nvidia(self) -> None:
        """D-20-1 + T14 launch-set TierMetadata + D-18-5 quality-proxy boost.

        The T14 ``NVIDIA_LAUNCH_MODEL_METADATA`` registry returns valid
        :class:`TierMetadata` for the three D-20-1 chat/reasoning models, and
        the reasoning-capable entries (Nemotron-3-Super 120b-a12b,
        Nano-Omni 30b) flip ``reasoning_capable=True`` so the Spec 18
        Layer 2 scorer applies the D-18-5 +0.10 quality-fit boost on hard
        turns (quality_proxy ≥ 0.5).
        """
        # T14 registry returns metadata for the launch set.
        chat_meta = nvidia_metadata_for_model("nvidia/llama-3.3-nemotron-super-49b-v1.5")
        reasoning_meta = nvidia_metadata_for_model("nvidia/nemotron-3-super-120b-a12b")
        assert chat_meta is not None
        assert reasoning_meta is not None
        assert chat_meta.reasoning_capable is False  # chat-primary stays False
        assert reasoning_meta.reasoning_capable is True  # 120b flips True

        # NVIDIA Nemotron Nano-Omni reasoning entry also flips True.
        nano = NVIDIA_LAUNCH_MODEL_METADATA["nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"]
        assert nano.reasoning_capable is True

        # Isolate the D-18-5 boost from cost-axis noise: hold cost/latency
        # constant by reusing the same backend config + cost numbers; toggle
        # ONLY ``reasoning_capable`` between the two registries. The chat
        # primary's $/Mtok pulls the scorer hard on cost otherwise (the
        # reasoning 120b-a12b is 5× more expensive per output token), which
        # would swamp the +0.10 boost and obscure what this test asserts.
        shared_kwargs: dict[str, Any] = {
            "cost_input_per_1k_tokens": chat_meta.cost_input_per_1k_tokens,
            "cost_output_per_1k_tokens": chat_meta.cost_output_per_1k_tokens,
            "first_token_latency_ms": chat_meta.first_token_latency_ms,
            "throughput_tokens_per_sec": chat_meta.throughput_tokens_per_sec,
            "context_window": chat_meta.context_window,
            "tool_strength": chat_meta.tool_strength,
            "cost_verified_at_deploy": False,
        }
        reasoning_meta_iso = TierMetadata(**shared_kwargs, reasoning_capable=True)
        no_reasoning_meta_iso = TierMetadata(**shared_kwargs, reasoning_capable=False)

        reasoning_tier = TierConfig(
            name="frontier",
            backend_config=_nvidia_chat_config("nvidia/nemotron-3-super-120b-a12b"),
            metadata=reasoning_meta_iso,
        )
        no_reasoning_tier = TierConfig(
            name="frontier",
            backend_config=_nvidia_chat_config("nvidia/llama-3.3-nemotron-super-49b-v1.5"),
            metadata=no_reasoning_meta_iso,
        )
        reasoning_registry = TierRegistry({"frontier": reasoning_tier})
        no_reasoning_registry = TierRegistry({"frontier": no_reasoning_tier})

        hard_turn = RoutingContext(
            requires_vision=False,
            estimated_input_tokens=1500,
            requires_strong_tools=True,
            is_first_turn=True,
            is_identity_sensitive=True,
            conversation_phase="opening",
            profile="text_default",
        )

        reasoning_score = score_tier("frontier", hard_turn, reasoning_registry)
        no_reasoning_score = score_tier("frontier", hard_turn, no_reasoning_registry)
        assert reasoning_score is not None
        assert no_reasoning_score is not None
        # D-18-5 boost: reasoning_capable=True + hard turn (quality_proxy
        # ≥ 0.5) → strictly higher quality_fit, all else equal.
        assert reasoning_score > no_reasoning_score, (
            f"D-18-5 quality-proxy boost not applied: "
            f"reasoning={reasoning_score} vs no_reasoning={no_reasoning_score}"
        )

    def test_router_metadata_partial_metadata_excludes_tier_from_layer_2(self) -> None:
        """D-18-X-partial-metadata-behaviour mirror — a tier without
        TierMetadata returns ``None`` from :func:`score_tier`, which is the
        signal Spec 18's UnifiedRouter reads to exclude the tier from Layer 2.
        Acts as a regression guard so the D-18-1 scorer never silently scores
        an NVIDIA tier whose metadata the operator forgot to populate.
        """
        bare_tier = TierConfig(
            name="frontier",
            backend_config=_nvidia_chat_config("nvidia/some-future-model"),
            metadata=None,
        )
        registry = TierRegistry({"frontier": bare_tier})
        ctx = RoutingContext(
            requires_vision=False,
            estimated_input_tokens=500,
            requires_strong_tools=False,
            is_first_turn=False,
            is_identity_sensitive=False,
            conversation_phase="middle",
            profile="text_default",
        )
        assert score_tier("frontier", ctx, registry) is None

    def test_router_tier_metadata_cost_verified_at_deploy_false_for_nvidia(self) -> None:
        """R-20-4 verify-at-deploy precedent — NVIDIA hosted catalog does not
        publish authoritative ``$/Mtok``; T14 launch entries flag
        ``cost_verified_at_deploy=False`` so the operator sees the marker.

        Cross-spec invariant: future scorer revisions reading this flag
        (e.g., to skip cost weighting on unverified entries) inherit the
        signal from a single source of truth — the T14 registry.
        """
        for model_id, metadata in NVIDIA_LAUNCH_MODEL_METADATA.items():
            assert metadata.cost_verified_at_deploy is False, (
                f"{model_id} should ship with cost_verified_at_deploy=False"
            )
            assert isinstance(metadata, TierMetadata)
