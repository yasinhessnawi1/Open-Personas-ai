"""The rule-based router (T04; D-05-5).

Picks a model tier — ``"frontier"``, ``"mid"``, or ``"small"`` — for each turn.
This is a small Python module, not a model and not magic (architecture §5.3).
The classifiers are keyword/regex matching; there is no ML, no embeddings, no
trained router. When a decision is wrong it fails *visibly* — you read the rules
and see why — and the fix is one line in one function.

Precedence (spec §6):
    1. per-persona ``routing.tier_for_generation`` override (when not ``"auto"``)
    2. first turn (``turn_count == 0``) → frontier (establish identity well)
    3. boilerplate → small
    4. persona-critical → frontier
    5. default → mid
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persona.schema.conversation import Conversation
    from persona.schema.persona import Persona

__all__ = ["Router"]

# Acknowledgement / reformat phrases that route to the small tier (spec §6.1).
# Word-boundary matched, case-insensitive. Multi-word phrases are matched as a
# contiguous span. Extend by adding an entry — that's the whole maintenance story.
_BOILERPLATE_PATTERNS: tuple[str, ...] = (
    r"\bok\b",
    r"\bokay\b",
    r"\bthanks\b",
    r"\bthank you\b",
    r"\bthx\b",
    r"\bgot it\b",
    r"\bsounds good\b",
    r"\bgreat\b",
    r"\bperfect\b",
    r"\bnoted\b",
    r"\bunderstood\b",
    r"\breformat\b",
    r"\brephrase\b",
    r"\bsummari[sz]e (that|this|it)\b",
    r"\btry again\b",
)

# Identity / constraint-pressuring phrases that route to frontier (spec §6.1).
_CRITICAL_PATTERNS: tuple[str, ...] = (
    r"\bwho are you\b",
    r"\bwhat are you\b",
    r"\bwhat'?s your (background|role|name|purpose)\b",
    r"\btell me about yourself\b",
    r"\bare you (an? )?(ai|bot|robot|model|human)\b",
    r"\bignore (your|the|all|previous|prior)( \w+)* (instructions?|rules?|constraints?)\b",
    r"\bforget (your|the|all|previous)( \w+)* (instructions?|rules?)\b",
    r"\bjust give me the answer\b",
    r"\bdrop the (act|persona|character)\b",
    r"\bstop pretending\b",
    r"\bbreak character\b",
)

# Minimum length for a persona-derived keyword to count (drops stopwords-ish
# short tokens). Keywords come from the persona's constraints + worldview.
_MIN_KEYWORD_LEN = 5
_WORD_RE = re.compile(rf"[a-zA-Z]{{{_MIN_KEYWORD_LEN},}}")


class Router:
    """Chooses a model tier per turn via readable rules (architecture §5.3).

    Stateless: every input it needs is passed to :meth:`choose`. The persona's
    keyword set is derived per call (D-05-5) — at v0.1 volume the cost is
    negligible and it keeps the router free of per-persona state.
    """

    def choose(self, persona: Persona, message: str, conversation: Conversation) -> str:
        """Return the tier name for this turn.

        Args:
            persona: The active persona (its ``routing`` override, ``identity``
                constraints, and ``worldview`` feed the decision).
            message: The user's message for this turn.
            conversation: The live conversation (its ``turn_count`` decides the
                first-turn rule).

        Returns:
            One of ``"frontier"``, ``"mid"``, ``"small"``.
        """
        override = persona.routing.tier_for_generation
        if override != "auto":
            return override

        if conversation.turn_count == 0:
            return "frontier"

        if self._is_boilerplate(message):
            return "small"

        if self._is_persona_critical(message, persona):
            return "frontier"

        return "mid"

    def _is_boilerplate(self, message: str) -> bool:
        """True for acknowledgements, reformat/clarify requests — routine work."""
        text = message.strip().lower()
        return any(re.search(p, text) for p in _BOILERPLATE_PATTERNS)

    def _is_persona_critical(self, message: str, persona: Persona) -> bool:
        """True for identity questions, constraint pressure, or worldview hits.

        Two parts: static identity/constraint-pressure phrases, plus a check
        against keywords derived from the persona's own constraints and
        worldview claims (spec §6.1). A message touching the persona's
        contested/worldview territory deserves the frontier tier.
        """
        text = message.lower()
        if any(re.search(p, text) for p in _CRITICAL_PATTERNS):
            return True
        keywords = self._persona_keywords(persona)
        if not keywords:
            return False
        message_words = {w.lower() for w in _WORD_RE.findall(text)}
        return bool(keywords & message_words)

    def _persona_keywords(self, persona: Persona) -> set[str]:
        """Significant words drawn from the persona's constraints + worldview.

        Lowercased, length ≥ :data:`_MIN_KEYWORD_LEN`. Derived per call — the
        persona may differ between calls (one process serves many personas).
        """
        keywords: set[str] = set()
        for constraint in persona.identity.constraints:
            keywords.update(w.lower() for w in _WORD_RE.findall(constraint))
        for claim in persona.worldview:
            keywords.update(w.lower() for w in _WORD_RE.findall(claim.claim))
            if claim.domain:
                keywords.update(w.lower() for w in _WORD_RE.findall(claim.domain))
        return keywords
