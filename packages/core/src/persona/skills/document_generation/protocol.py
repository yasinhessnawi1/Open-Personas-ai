"""``DocumentHandler`` Protocol + the ``FormatHandler`` descriptor (D-24-1).

Reading B (D-24-1): document generation is an **instruction-pack** skill. The
model writes Python that runs in the ``code_execution`` sandbox; persona-core
performs **no** in-process rendering and takes **no** rendering dependency. A
handler is therefore a *dispatch descriptor* — it names a format, its output
file extension, the sandbox library the ``SKILL.md`` teaches the model to use,
and the supplement topics staged for that format.

The spec's ``DocumentHandler.generate(content_spec, template) -> bytes`` wording
is **reconciled here as a dispatch contract**, not a runtime method: the bytes
are produced when the sandbox runs the model's code, not by persona-core. The
Protocol is deliberately shaped so a *future* in-process handler type (one that
genuinely renders bytes in the runtime) is not precluded — such a type would
extend this Protocol with its own ``render(...) -> bytes`` seam behind a
separate optional interface. **None is built in Spec 24.**
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["DocumentHandler", "FormatHandler"]


@runtime_checkable
class DocumentHandler(Protocol):
    """Instruction-dispatch contract for one document format (Reading B).

    Members are read-only (``@property``) so an immutable frozen descriptor
    such as :class:`FormatHandler` satisfies the Protocol structurally.

    Attributes:
        format_key: The ``format`` parameter value the persona passes to
            ``use_skill(document_generation, {"format": ...})`` (e.g. ``"docx"``).
        output_extension: The produced file's extension, leading dot included
            (e.g. ``".docx"``). The ``SKILL.md`` teaches the model to write to
            ``/workspace/out/<name><output_extension>``.
        library: The sandbox library + pin the ``SKILL.md`` teaches the model
            to use (e.g. ``"python-docx==1.1.2"``), or ``"stdlib"`` for the
            pure-text formats. This is documentation of the **sandbox** library;
            it is never imported by persona-core.
        supplement_topics: Topic names whose deep guidance ships as
            ``builtin/document_generation/supplements/<format>-<topic>.md`` and
            is staged into the sandbox for the model to read on demand.
    """

    @property
    def format_key(self) -> str: ...

    @property
    def output_extension(self) -> str: ...

    @property
    def library(self) -> str: ...

    @property
    def supplement_topics(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class FormatHandler:
    """Immutable concrete :class:`DocumentHandler` descriptor.

    A frozen value object — handlers are constants, not stateful objects. One
    instance per format lives in ``handlers/<format>.py`` and is registered in
    :mod:`persona.skills.document_generation.registry`.
    """

    format_key: str
    output_extension: str
    library: str
    supplement_topics: tuple[str, ...] = ()
