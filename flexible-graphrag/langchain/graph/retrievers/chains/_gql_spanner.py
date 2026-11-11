"""Spanner Graph GQL QA chain builder."""
from __future__ import annotations

from typing import Any


def build_gql_spanner(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """SpannerGraphQAChain (langchain-google-spanner): generates, verifies and fixes GQL."""
    from langchain_google_spanner import SpannerGraphQAChain
    return SpannerGraphQAChain.from_llm(llm=llm, graph=graph, verbose=False,
                                        return_intermediate_steps=include_intermediate,
                                        allow_dangerous_requests=True)
