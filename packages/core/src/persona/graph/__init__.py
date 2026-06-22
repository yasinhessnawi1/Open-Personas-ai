"""The user-scoped shared knowledge-graph store (Spec K0, direction 3).

The "bigger brain" about the user that all of a user's personas read from and
write to: concept-nodes connected by typed links (semantic / entity / temporal /
causal), kept coherent by canonical-entity resolution + accumulate-via-merge,
persisted with Postgres as the source of truth and an optional turbovec dense
index over the durable float32 embeddings.

T1 ships the domain primitives + exceptions; later tasks add the store/index
ports, the Postgres transport, the entity resolver, the merge engine, and the
pgvector/turbovec adapters.
"""

from __future__ import annotations

from persona.graph.calibration import ThresholdResult, best_threshold, sweep_thresholds
from persona.graph.config import GraphSettings
from persona.graph.entities import PostgresEntityRegistry
from persona.graph.errors import (
    EntityResolutionError,
    GraphError,
    GraphIndexError,
    GraphRebuildError,
    NodeMergeError,
)
from persona.graph.fusion import HybridResult, reciprocal_rank_fusion
from persona.graph.index import make_graph_index
from persona.graph.index_pgvector import PgvectorGraphIndex
from persona.graph.index_turbovec import TurbovecGraphIndex, exact_rerank
from persona.graph.merge import MergeEngine
from persona.graph.models import (
    NODE_ID_INDEX_WIDTH,
    CanonicalEntity,
    ConceptNode,
    EntityAlias,
    LinkType,
    NodeKind,
    NodeProvenance,
    TypedLink,
    make_edge_id,
    make_entity_id,
    make_node_id,
)
from persona.graph.protocol import (
    EntityCandidate,
    EntityRegistry,
    GraphIndex,
    GraphStore,
    KnowledgeCandidate,
    MergeAction,
    MergeOutcome,
    ProposedLink,
    ResolutionDecision,
    ResolutionVerdict,
    UpdateIntent,
)
from persona.graph.retrieval import HybridRetriever
from persona.graph.store import PostgresGraphStore, build_graph_store

__all__ = [
    "NODE_ID_INDEX_WIDTH",
    "CanonicalEntity",
    "ConceptNode",
    "EntityAlias",
    "EntityCandidate",
    "EntityRegistry",
    "EntityResolutionError",
    "GraphError",
    "GraphIndex",
    "GraphIndexError",
    "GraphRebuildError",
    "GraphSettings",
    "GraphStore",
    "HybridResult",
    "HybridRetriever",
    "KnowledgeCandidate",
    "LinkType",
    "MergeAction",
    "MergeEngine",
    "MergeOutcome",
    "NodeKind",
    "NodeMergeError",
    "NodeProvenance",
    "PgvectorGraphIndex",
    "PostgresEntityRegistry",
    "PostgresGraphStore",
    "ProposedLink",
    "TurbovecGraphIndex",
    "ResolutionDecision",
    "ResolutionVerdict",
    "ThresholdResult",
    "TypedLink",
    "UpdateIntent",
    "best_threshold",
    "build_graph_store",
    "exact_rerank",
    "reciprocal_rank_fusion",
    "make_edge_id",
    "make_entity_id",
    "make_graph_index",
    "make_node_id",
    "sweep_thresholds",
]
