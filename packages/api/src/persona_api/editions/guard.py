"""The safety guard (Spec 33, §2.4 / D-33-4 / D-33-X-public-bind-detection).

Community defaults to *no auth*. If such a process is bound to a non-loopback
(public) address, anyone on the network can drive it — burning the operator's
model API keys against an open, unauthenticated instance. The guard refuses to
start in that configuration unless the operator has explicitly opted in via
``PERSONA_ALLOW_PUBLIC_NOAUTH=1``. Conservative by design: anything not provably
loopback is treated as public.

Cloud (auth enabled) is never gated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.logging import get_logger

from persona_api.config import Edition
from persona_api.errors import PublicNoAuthRefusedError

if TYPE_CHECKING:
    from persona_api.config import APIConfig

__all__ = ["check_public_noauth_guard"]

_LOG = get_logger("api.editions.guard")

# Provably-loopback bind hosts. Everything else (including 0.0.0.0 / :: =
# all-interfaces, and any specific public IP/hostname) is treated as public.
_LOOPBACK_HOSTS = frozenset({"", "127.0.0.1", "::1", "localhost"})


def _is_loopback(host: str) -> bool:
    """Whether ``host`` is a provably-loopback bind address."""
    h = host.strip().lower()
    # strip an IPv6 zone id / brackets that a bind string might carry
    h = h.removeprefix("[").removesuffix("]")
    if h.startswith("127."):
        return True
    return h in _LOOPBACK_HOSTS


def check_public_noauth_guard(config: APIConfig) -> None:
    """Refuse to start a community/no-auth process on a public bind (D-33-4).

    Raises:
        PublicNoAuthRefusedError: community edition + non-loopback ``host`` +
            ``PERSONA_ALLOW_PUBLIC_NOAUTH`` unset.
    """
    if config.edition is not Edition.community:
        return  # cloud has an auth wall; never gated
    if _is_loopback(config.host):
        return  # local single-user — safe
    if config.allow_public_noauth:
        _LOG.warning(
            "community/no-auth bound to a PUBLIC host {host} — "
            "PERSONA_ALLOW_PUBLIC_NOAUTH override is set; the instance is OPEN "
            "and UNAUTHENTICATED. Use PERSONA_EDITION=cloud for a shared deploy.",
            host=config.host,
        )
        return
    raise PublicNoAuthRefusedError(
        "refusing to start: community edition has no auth wall and the bind host "
        f"{config.host!r} is not loopback. Set PERSONA_ALLOW_PUBLIC_NOAUTH=1 to "
        "override (NOT recommended), or run PERSONA_EDITION=cloud for a public deploy.",
        context={"host": config.host, "edition": config.edition.value},
    )
