"""The full-text index's text analyzer (SEARCH_ANALYZER), as Elasticsearch / OpenSearch index settings.

Set as the index's default analyzer when the index is created, so it applies to the text field and
to queries against it. Values:

- ``standard``: the engine's standard analyzer (keeps every word).
- ``<language>_stopwords`` (``english_stopwords``, ``french_stopwords``, ...): standard tokenizing and
  lower-casing, then that language's built-in stopword list removed; no stemming. For English the list
  also drops question words ("who", "how", "what", ...), which otherwise match any chunk using them.
- any built-in analyzer name (``english``, ``french``, ...): the engine's language analyzer, which also
  stems words ("organized" -> "organ", so it matches "organization").
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Question and request words a search phrased as a question carries: Lucene's _english_ list keeps them
_ENGLISH_QUESTION_WORDS = [
    "who", "whom", "whose", "what", "which", "when", "where", "why", "how",
    "do", "does", "did", "is", "are", "was", "were", "be", "been", "has", "have", "had",
    "can", "could", "would", "should", "about", "tell", "me", "my", "i", "you",
    "list", "show", "give", "find", "any", "all",
]


def analysis_settings(analyzer: Optional[str]) -> Optional[Dict[str, Any]]:
    """Index settings for *analyzer*, or None for the engine's standard analyzer."""
    name = (analyzer or "standard").strip().lower()
    if name == "standard":
        return None
    if name.endswith("_stopwords"):
        language = name[: -len("_stopwords")]
        stopwords = [f"_{language}_"] + (_ENGLISH_QUESTION_WORDS if language == "english" else [])
        filters = ["lowercase", "fg_stop"]
        stop_filters: Dict[str, Any] = {"fg_stop": {"type": "stop", "stopwords": stopwords}}
        if language == "english":
            # "Acme's" -> "acme"
            stop_filters["fg_possessive"] = {"type": "stemmer", "language": "possessive_english"}
            filters.insert(0, "fg_possessive")
        return {"analysis": {"filter": stop_filters,
                             "analyzer": {"default": {"type": "custom", "tokenizer": "standard", "filter": filters}}}}
    return {"analysis": {"analyzer": {"default": {"type": name}}}}
