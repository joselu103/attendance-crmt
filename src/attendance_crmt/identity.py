"""Requester identity abstractions independent of server composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Requester:
    """The server-derived identity acting through an MCP request."""

    actor_id: str
    roles: frozenset[str]


class RequesterResolver(Protocol):
    """Resolve the requester for the current transport context."""

    def resolve(self, context: Any) -> Requester:
        """Return the requester identity for one tool invocation."""
        ...


@dataclass(frozen=True)
class StaticRequesterResolver:
    """Development-only resolver until transport authentication is available."""

    requester: Requester

    def resolve(self, context: Any) -> Requester:
        """Return the configured MVP requester identity."""
        return self.requester


def create_mvp_requester_resolver() -> StaticRequesterResolver:
    """Create the fixed read-only MVP administrator requester."""
    return StaticRequesterResolver(
        Requester(actor_id="mvp-admin", roles=frozenset({"admin"}))
    )
