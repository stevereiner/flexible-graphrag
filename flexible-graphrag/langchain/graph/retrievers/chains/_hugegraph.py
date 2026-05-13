"""HugeGraph Cypher chain builder (via custom REST view)."""

import logging
from typing import Any

_logger = logging.getLogger(__name__)


def build_cypher_hugegraph(graph: Any, llm: Any, include_intermediate: bool, common: dict) -> Any:
    """HugeGraph chain: routes Cypher through the /graphs/{graph}/cypher REST endpoint."""
    import requests as _req
    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
    from langchain_community.graphs.graph_store import GraphStore as _GS
    from langchain_core.prompts import PromptTemplate

    _hg = graph

    def _build_hg_schema_str() -> str:
        try:
            _user = getattr(_hg, "username", None)
            _pwd  = getattr(_hg, "password", None)
            _auth = (_user, _pwd) if _user and _pwd else None
            _base = f"http://{_hg.address}:{_hg.port}/graphs/{_hg.graph}/schema"
            vl_data = _req.get(f"{_base}/vertexlabels", auth=_auth, timeout=10).json()
            el_data = _req.get(f"{_base}/edgelabels",   auth=_auth, timeout=10).json()
            node_lines = []
            for vl in vl_data.get("vertexlabels", []):
                props = ", ".join(f"{p}: STRING" for p in vl.get("properties", []))
                node_lines.append(f"- {vl['name']} {{{props}}}")
            rel_lines = []
            for el in el_data.get("edgelabels", []):
                src  = el.get("source_label", "__Entity__")
                tgt  = el.get("target_label", "__Entity__")
                name = el.get("name", "")
                if name and name != "TEST_REL":
                    rel_lines.append(f"(:{src})-[:{name}]->(:{tgt})")
            return (
                "Node properties:\n"
                + "\n".join(node_lines)
                + "\n\nRelationship types:\n"
                + "\n".join(rel_lines)
            )
        except Exception as _schema_exc:
            _logger.debug("HugeGraph schema build failed: %s", _schema_exc)
            return _hg.schema or ""

    _HG_SCHEMA = _build_hg_schema_str()

    _HG_CYPHER_TEMPLATE = """\
You are an expert Cypher query writer for Apache HugeGraph.
Given the schema below, write a Cypher query to answer the question.

Schema:
{schema}

Important rules — read carefully:
- ALL entity nodes use the label __Entity__, regardless of type (Person, Organization, etc.).
  Never use labels like :Person, :Organization, :Location — they do not exist.
- To filter by entity type use: WHERE n.node_type = 'Person'
- The `name` property holds the entity's display name. Always use n.name (not n.id).
- Use case-insensitive partial matching for string comparisons:
    WHERE toLower(n.name) CONTAINS toLower("value")
- NEVER use UNION or UNION ALL — HugeGraph requires identical column names across
  all UNION arms and will reject queries that don't match. Use OPTIONAL MATCH instead.
- Typical query patterns:
    # Who works for a company
    MATCH (p:__Entity__)-[:WORKS_FOR]->(o:__Entity__)
    WHERE toLower(o.name) CONTAINS 'acme'
    RETURN p.name, p.node_type

    # List all of an org's departments, locations, and leaders in one query
    MATCH (o:__Entity__) WHERE toLower(o.name) CONTAINS 'acme'
    OPTIONAL MATCH (o)-[:HAS_DEPARTMENT]->(d:__Entity__)
    OPTIONAL MATCH (o)-[:HAS_LOCATION]->(l:__Entity__)
    OPTIONAL MATCH (o)-[:LED_BY]->(ldr:__Entity__)
    RETURN o.name AS org,
           d.name AS department,
           l.name AS location,
           ldr.name AS leader

    # All relationships out of an entity
    MATCH (o:__Entity__)-[r]->(related:__Entity__)
    WHERE toLower(o.name) CONTAINS 'acme'
    RETURN type(r) AS relationship, related.name, related.node_type
    ORDER BY relationship

- Output ONLY the raw Cypher query — no explanation, no markdown fences.

Question: {question}
Cypher query:"""

    try:
        _hg_cypher_prompt = PromptTemplate(
            input_variables=["schema", "question"],
            template=_HG_CYPHER_TEMPLATE,
        )
    except Exception:
        _hg_cypher_prompt = None

    class _HugeGraphCypherView(_GS):
        """Routes query() to HugeGraph's openCypher REST endpoint.

        Inherits GraphStore so pydantic's isinstance check inside
        GraphCypherQAChain passes. Implements all abstract methods.
        HugeGraph 1.x Cypher endpoint:
            POST /graphs/{graph}/cypher   Content-Type: application/json
            body = raw Cypher query string
        Response envelope: {"status": {"code": 200}, "result": {"data": [...]}}
        """

        @property
        def get_schema(self) -> str:
            return _HG_SCHEMA

        @property
        def get_structured_schema(self) -> dict:
            return self.structured_schema

        @property
        def structured_schema(self) -> dict:
            base = f"http://{_hg.address}:{_hg.port}/graphs/{_hg.graph}/schema"
            _user = getattr(_hg, "username", None)
            _pwd  = getattr(_hg, "password", None)
            _auth = (_user, _pwd) if _user and _pwd else None
            node_props: dict = {}
            relationships: list = []
            try:
                vl = _req.get(f"{base}/vertexlabels", auth=_auth, timeout=10)
                for vl_item in vl.json().get("vertexlabels", []):
                    name = vl_item.get("name", "")
                    node_props[name] = [
                        {"property": p, "type": "STRING"}
                        for p in vl_item.get("properties", [])
                    ]
            except Exception:
                pass
            try:
                el = _req.get(f"{base}/edgelabels", auth=_auth, timeout=10)
                for el_item in el.json().get("edgelabels", []):
                    relationships.append({
                        "start": el_item.get("source_label", "__Entity__"),
                        "type":  el_item.get("name", ""),
                        "end":   el_item.get("target_label", "__Entity__"),
                    })
            except Exception:
                pass
            return {
                "node_props":    node_props,
                "rel_props":     {},
                "relationships": relationships,
                "metadata":      {},
            }

        def query(self, cypher_query: str, params: dict = {}) -> list:
            url = f"http://{_hg.address}:{_hg.port}/graphs/{_hg.graph}/cypher"
            _user = getattr(_hg, "username", None)
            _pwd  = getattr(_hg, "password", None)
            _auth = (_user, _pwd) if _user and _pwd else None
            try:
                resp = _req.post(
                    url,
                    data=cypher_query,
                    headers={"Content-Type": "application/json"},
                    auth=_auth,
                    timeout=30,
                )
                resp.raise_for_status()
                body = resp.json()
                if body.get("status", {}).get("code", 200) != 200:
                    _logger.warning(
                        "HugeGraph Cypher error: %s | query: %.200s",
                        body["status"].get("message", ""),
                        cypher_query,
                    )
                    return []
                return body.get("result", {}).get("data") or []
            except Exception as exc:
                _logger.warning(
                    "HugeGraph Cypher request failed: %s | query: %.200s",
                    exc, cypher_query,
                )
                return []

        def refresh_schema(self) -> None:
            _hg.refresh_schema()

        def add_graph_documents(self, graph_documents, include_source=False):
            pass  # write path uses HugeGraphAdapter.add_graph_documents directly

    _hg_view = _HugeGraphCypherView()
    _chain_kwargs = {k: v for k, v in common.items() if k != "graph"}
    if _hg_cypher_prompt:
        _chain_kwargs["cypher_prompt"] = _hg_cypher_prompt
    chain = GraphCypherQAChain.from_llm(graph=_hg_view, **_chain_kwargs)

    try:
        chain.graph_schema = _HG_SCHEMA
    except Exception:
        pass

    _hg_original_query = _hg_view.query

    def _hg_split_union(cypher: str) -> list:
        """Execute each UNION arm separately and merge results."""
        import re as _re
        arms = _re.split(r'\bUNION(?:\s+ALL)?\b', cypher, flags=_re.IGNORECASE)
        merged: list = []
        seen: set = set()
        for arm in arms:
            arm = arm.strip()
            if not arm:
                continue
            try:
                rows = _hg_original_query(arm)
                for row in rows:
                    key = str(row)
                    if key not in seen:
                        seen.add(key)
                        merged.append(row)
            except Exception as _exc:
                _logger.debug("HugeGraph UNION arm failed: %s | arm: %.200s", _exc, arm)
        return merged

    def _hg_logged_query(cypher: str, *args, **kwargs):
        _logger.debug("Generated cypher query:\n%s", cypher)
        import re as _re
        if _re.search(r'\bUNION\b', cypher, flags=_re.IGNORECASE):
            _logger.debug("HugeGraph: rewriting UNION query into separate sub-queries")
            return _hg_split_union(cypher)
        return _hg_original_query(cypher, *args, **kwargs)

    _hg_view.query = _hg_logged_query  # type: ignore[method-assign]

    return chain
