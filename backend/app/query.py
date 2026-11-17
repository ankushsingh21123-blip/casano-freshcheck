"""Deterministic query derivation: keywords from question + answer.

No LLM is involved. Terms are lowercased, stopwords are removed, and the
remaining terms are ranked by a fixed score (question occurrences count
double) with alphabetical tie-breaking, so the same input always yields
the same query.
"""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    {
        "a", "about", "above", "after", "again", "against", "all", "am", "an",
        "and", "any", "are", "as", "at", "be", "because", "been", "before",
        "being", "below", "between", "both", "but", "by", "can", "could",
        "did", "do", "does", "doing", "down", "during", "each", "few", "for",
        "from", "further", "had", "has", "have", "having", "he", "her",
        "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
        "in", "into", "is", "it", "its", "itself", "let", "me", "more",
        "most", "my", "myself", "nor", "of", "on", "once", "only", "or",
        "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
        "same", "she", "should", "so", "some", "such", "than", "that",
        "the", "their", "theirs", "them", "themselves", "then", "there",
        "these", "they", "this", "those", "through", "to", "too", "under",
        "until", "up", "very", "was", "we", "were", "what", "when", "where",
        "which", "while", "who", "whom", "why", "with", "would", "you",
        "your", "yours", "yourself", "yourselves", "is", "are", "was",
        "were", "has", "have", "had", "will", "would", "shall", "may",
        "might", "must", "also", "currently", "please", "tell", "give",
        "show", "know", "per", "via",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
MAX_TERMS = 8
MAX_QUERY_LENGTH = 200


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens, stopwords and 1-2 char tokens removed."""
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]


def derive_query(question: str, answer: str) -> str:
    """Build a deterministic search query from question + answer.

    Question terms score double. Ties break alphabetically. The result is
    capped at MAX_TERMS terms and MAX_QUERY_LENGTH characters. When no
    content terms survive filtering, the question text itself (truncated)
    is used so the query is never empty.
    """
    question_terms = tokenize(question)
    answer_terms = tokenize(answer)

    scores: dict[str, int] = {}
    for term in question_terms:
        scores[term] = scores.get(term, 0) + 2
    for term in answer_terms:
        scores[term] = scores.get(term, 0) + 1

    if not scores:
        fallback = " ".join(question.split())[:MAX_QUERY_LENGTH].strip()
        return fallback

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top_terms = [term for term, _ in ranked[:MAX_TERMS]]
    query = " ".join(top_terms)
    return query[:MAX_QUERY_LENGTH].strip()
