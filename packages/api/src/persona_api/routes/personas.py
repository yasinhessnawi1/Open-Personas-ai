"""Persona CRUD + LLM-assisted authoring routes (spec 08, T07, §5.1).

Every route depends on ``get_current_user`` (which sets the RLS contextvar, so
the service's engine transactions are tenant-scoped — D-08-1) and reads the
RLS engine + embedder from ``app.state`` (attached by the lifespan). The
business logic lives in the services; the routes are thin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from persona_api.auth import AuthenticatedUser, get_current_user
from persona_api.middleware.rate_limit import rate_limit
from persona_api.schemas import (
    AuthorPersonaRequest,
    CreatePersonaRequest,
    PersonaDetail,
    PersonaSummary,
    UpdatePersonaRequest,
)
from persona_api.services import audit_service, authoring_service, credits_service, persona_service

router = APIRouter(prefix="/v1/personas", tags=["personas"])


def _persona_detail(row: dict[str, object]) -> PersonaDetail:
    avatar = row.get("avatar_url")
    return PersonaDetail(
        id=str(row["id"]),
        yaml=str(row["yaml"]),
        schema_version=str(row["schema_version"]),
        avatar_url=str(avatar) if avatar is not None else None,
        created_at=row["created_at"],  # type: ignore[arg-type]
        updated_at=row["updated_at"],  # type: ignore[arg-type]
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PersonaDetail)
async def create_persona(
    body: CreatePersonaRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PersonaDetail:
    """Create a persona from YAML; populate its memory stores (D-08-8)."""
    persona_id = persona_service.create_persona(
        rls_engine=request.app.state.rls_engine,
        embedder=request.app.state.embedder,
        audit_root=request.app.state.audit_root,
        owner_id=user.id,
        yaml_str=body.yaml,
        avatar_url=body.avatar_url,
    )
    audit_service.record(
        engine=request.app.state.rls_engine,
        user_id=user.id,
        action="persona.create",
        target=persona_id,
    )
    row = persona_service.get_persona(
        rls_engine=request.app.state.rls_engine, persona_id=persona_id
    )
    return _persona_detail(row)


@router.post("/author", response_model=PersonaDetail, dependencies=[Depends(rate_limit("author"))])
async def author_persona(
    body: AuthorPersonaRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PersonaDetail:
    """Generate a draft persona from a description, then create it (§6.3)."""
    backend = request.app.state.tier_registry.get(request.app.state.authoring_tier)
    yaml_str = await authoring_service.author_persona_yaml(backend, body.description)
    persona_id = persona_service.create_persona(
        rls_engine=request.app.state.rls_engine,
        embedder=request.app.state.embedder,
        audit_root=request.app.state.audit_root,
        owner_id=user.id,
        yaml_str=yaml_str,
    )
    # Flat credit deduction for the frontier-model authoring call (§11 risk).
    credits_service.deduct(
        rls_engine=request.app.state.rls_engine,
        user_id=user.id,
        amount=request.app.state.config.authoring_credit_cost,
        reason="persona_authoring",
    )
    audit_service.record(
        engine=request.app.state.rls_engine,
        user_id=user.id,
        action="persona.author",
        target=persona_id,
    )
    row = persona_service.get_persona(
        rls_engine=request.app.state.rls_engine, persona_id=persona_id
    )
    return _persona_detail(row)


@router.get("", response_model=list[PersonaSummary])
async def list_personas(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: ARG001 — RLS via contextvar
    limit: int = 50,
    offset: int = 0,
) -> list[PersonaSummary]:
    """List the caller's personas (paginated; RLS-scoped)."""
    rows = persona_service.list_personas(
        rls_engine=request.app.state.rls_engine, limit=min(limit, 200), offset=offset
    )
    return [persona_service.summary_of(r) for r in rows]


@router.get("/{persona_id}", response_model=PersonaDetail)
async def get_persona(
    persona_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: ARG001 — RLS via contextvar
) -> PersonaDetail:
    """Get a persona's YAML + metadata (404 if not the caller's)."""
    row = persona_service.get_persona(
        rls_engine=request.app.state.rls_engine, persona_id=persona_id
    )
    return _persona_detail(row)


@router.patch("/{persona_id}", response_model=PersonaDetail)
async def update_persona(
    persona_id: str,
    body: UpdatePersonaRequest,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PersonaDetail:
    """Replace a persona's YAML (re-validated) and re-index its memory."""
    persona_service.update_persona(
        rls_engine=request.app.state.rls_engine,
        embedder=request.app.state.embedder,
        audit_root=request.app.state.audit_root,
        owner_id=user.id,
        persona_id=persona_id,
        yaml_str=body.yaml,
        avatar_url=body.avatar_url,
    )
    audit_service.record(
        engine=request.app.state.rls_engine,
        user_id=user.id,
        action="persona.update",
        target=persona_id,
    )
    row = persona_service.get_persona(
        rls_engine=request.app.state.rls_engine, persona_id=persona_id
    )
    return _persona_detail(row)


@router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(
    persona_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    """Delete a persona + all its conversations and memory (cascade)."""
    persona_service.delete_persona(rls_engine=request.app.state.rls_engine, persona_id=persona_id)
    audit_service.record(
        engine=request.app.state.rls_engine,
        user_id=user.id,
        action="persona.delete",
        target=persona_id,
    )
