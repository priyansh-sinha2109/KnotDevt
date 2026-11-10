from dataclasses import dataclass

from app.schemas.agents import Citation


@dataclass(frozen=True)
class ResolvedCitation:
    start: int
    end: int


def occurrences(excerpt: str, quote: str) -> list[int]:
    results = []
    offset = excerpt.find(quote)
    while offset >= 0:
        results.append(offset)
        offset = excerpt.find(quote, offset + 1)
    return results


def _context_matches(excerpt: str, citation: Citation, start: int, end: int) -> bool:
    if citation.prefix is not None:
        before = excerpt[max(0, start - len(citation.prefix)) : start]
        if before != citation.prefix:
            return False
    if citation.suffix is not None:
        after = excerpt[end : end + len(citation.suffix)]
        if after != citation.suffix:
            return False
    return True


def resolve_citation(excerpt: str, citation: Citation) -> ResolvedCitation | None:
    """Resolve only an exact, uniquely identified occurrence.

    Valid supplied offsets take precedence. Without valid offsets, a unique quote
    or a quote made unique by exact surrounding context is accepted. Repeated
    occurrences without a unique discriminator remain unresolved.
    """
    if citation.start is not None and citation.end is not None:
        if excerpt[
            citation.start : citation.end
        ] == citation.quote and _context_matches(
            excerpt, citation, citation.start, citation.end
        ):
            return ResolvedCitation(citation.start, citation.end)

    matches = [
        start
        for start in occurrences(excerpt, citation.quote)
        if _context_matches(excerpt, citation, start, start + len(citation.quote))
    ]
    if len(matches) != 1:
        return None
    start = matches[0]
    return ResolvedCitation(start, start + len(citation.quote))
