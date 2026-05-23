"""Match user-supplied tokens to OCI resources.

Spec §10 defines the precedence:
    1. exact OCID
    2. exact display_name
    3. display_name prefix
    4. OCID short-id (last 8..12 chars)

If multiple candidates remain at the same priority level, raise
``AmbiguousResource`` so the command layer can render the candidate list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class HasNameAndId(Protocol):
    @property
    def display_name(self) -> str: ...

    @property
    def id(self) -> str: ...


@dataclass(frozen=True)
class ResourceNotFound(LookupError):
    query: str
    profile: str
    region: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            f"Resource not found.\nProfile: {self.profile}\nRegion: {self.region}\n"
            f"Query: {self.query}"
        )


@dataclass(frozen=True)
class AmbiguousResource(LookupError):
    query: str
    candidates: tuple[HasNameAndId, ...]

    def __str__(self) -> str:  # pragma: no cover - trivial
        names = ", ".join(c.display_name for c in self.candidates)
        return f"Ambiguous resource {self.query!r}; candidates: {names}"


_SHORT_ID_MIN = 8
_SHORT_ID_MAX = 12


def is_ocid(token: str) -> bool:
    return token.startswith("ocid1.")


def match(
    query: str,
    resources: list[HasNameAndId],
    *,
    profile: str,
    region: str,
) -> HasNameAndId:
    """Resolve a user query to exactly one resource or raise.

    Args:
        query: user-supplied token.
        resources: candidate resources to match against.
        profile: OCI profile name, used to construct the not-found error.
        region: OCI region, used to construct the not-found error.
    """
    query = query.strip()
    if not query:
        raise ResourceNotFound(query=query, profile=profile, region=region)

    if is_ocid(query):
        for r in resources:
            if r.id == query:
                return r
        raise ResourceNotFound(query=query, profile=profile, region=region)

    exact_name = [r for r in resources if r.display_name == query]
    if len(exact_name) == 1:
        return exact_name[0]
    if len(exact_name) > 1:
        raise AmbiguousResource(query=query, candidates=tuple(exact_name))

    prefix_name = [r for r in resources if r.display_name.startswith(query)]
    if len(prefix_name) == 1:
        return prefix_name[0]
    if len(prefix_name) > 1:
        raise AmbiguousResource(query=query, candidates=tuple(prefix_name))

    if _SHORT_ID_MIN <= len(query) <= _SHORT_ID_MAX:
        short_id_hits = [r for r in resources if r.id.endswith(query)]
        if len(short_id_hits) == 1:
            return short_id_hits[0]
        if len(short_id_hits) > 1:
            raise AmbiguousResource(query=query, candidates=tuple(short_id_hits))

    raise ResourceNotFound(query=query, profile=profile, region=region)
