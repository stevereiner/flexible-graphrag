"""
Convert LlamaIndex KG extraction output (EntityNode / Relation) to an rdflib.Graph
plus a Turtle string for relation-property annotations.

Three annotation modes are supported, controlled by the ``annotation_syntax``
parameter:

``rdf_1.2`` (default) — RDF 1.2 inline annotation syntax (W3C Recommendation)
    Uses the ``{| prop value |}`` shorthand introduced in Turtle 1.2 / RDF 1.2.
    This is the preferred, standards-compliant way to annotate triples.

        LPG:  (Alice)-[:WORKS_FOR {since: 2020, role: "Engineer"}]->(TechCorp)

        Turtle 1.2 (RDF 1.2 annotation):
              :alice_johnson  onto:works_for  :techcorp
                  {| onto:since "2020"^^xsd:string ;
                     onto:role  "Engineer"^^xsd:string |} .

    The anonymous reifier ``{| |}`` desugars to:
        [] rdf:reifies <<( :alice_johnson onto:works_for :techcorp )>> ;
           onto:since "2020" ; onto:role "Engineer" .
    Supported by: Fuseki 5 (Jena 5), GraphDB 10+, Oxigraph 0.4+.

``rdf_star`` — Legacy RDF-star assertion syntax (pre-RDF-1.2 proposal)
    Uses ``<< <s> <p> <o> >> <prop> value .`` lines appended after the plain
    triples.  Still accepted by all three stores for backward compatibility, but
    ``rdf_1.2`` is preferred for new data.

``flat`` — Plain SPARQL 1.1 compound-predicate triples (widest compatibility)
    Relation properties are stored as plain triples on the subject with compound
    predicate names: ``<s>  onto:rel__prop  value .``
    Works with any SPARQL 1.1 triple store; no annotation semantics.

Note: rdflib 7.x does not support RDF 1.2 or RDF-star natively in its Graph API
or Turtle parser.  All annotation lines are built as raw strings and appended to
the rdflib-serialized base Turtle.  The combined string is handed directly to
each store adapter via store_rdf_annotations(turtle_str).
"""

import re
import logging
from typing import List, Optional, Any, Dict, Tuple

from rdflib import Graph, URIRef, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, XSD, OWL

logger = logging.getLogger(__name__)

# Default base namespace for extracted instance data
DEFAULT_BASE_NS = "https://integratedsemantics.org/flexible-graphrag/kg/"
DEFAULT_ONTO_NS = "https://integratedsemantics.org/flexible-graphrag/ontology#"


def _slugify(name: str) -> str:
    """Convert an entity name to a URI-safe slug.

    Examples:
        "Alice Johnson"  -> "alice_johnson"
        "TechCorp Inc."  -> "techcorp_inc"
        "WORKS_FOR"      -> "works_for"
    """
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9_]+", "_", slug)
    slug = slug.strip("_")
    return slug or "entity"


# Document-provenance keys injected by LlamaIndex node metadata — these describe
# *where* an entity was extracted from, not semantic properties of the entity or
# relation itself.  They are valid on entity nodes but must NOT appear as
# annotation properties on relation reifiers.
_PROVENANCE_KEYS: frozenset = frozenset({
    "file_path", "file_name", "file_type", "source",
    "modified_at", "modified at",
    "ref_doc_id", "doc_id", "conversion_method",
})


def _infer_xsd_type(value: Any, pred_key: str = None, xsd_type_map: dict = None) -> URIRef:
    """Map a Python value to the most appropriate XSD datatype.

    When ``xsd_type_map`` is provided (populated from OntologyManager.get_xsd_type_map()),
    the ontology-declared type for ``pred_key`` takes priority over Python type inference.
    This emits correctly-typed literals such as ``"2008-09-10"^^xsd:date`` instead of
    always falling back to ``xsd:string``.
    """
    if xsd_type_map and pred_key:
        declared = xsd_type_map.get(pred_key.upper())
        if declared:
            return URIRef(declared)
    if isinstance(value, bool):
        return XSD.boolean
    if isinstance(value, int):
        return XSD.integer
    if isinstance(value, float):
        return XSD.decimal
    return XSD.string


def _make_literal(value: Any, pred_key: str = None, xsd_type_map: dict = None) -> Literal:
    """Create an rdflib Literal with appropriate XSD datatype.

    Uses ontology-declared type when available (via xsd_type_map), otherwise
    falls back to Python type inference.
    """
    return Literal(value, datatype=_infer_xsd_type(value, pred_key=pred_key, xsd_type_map=xsd_type_map))


def _turtle_escape_string(value: str) -> str:
    """Escape a string value for safe embedding in a Turtle literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _turtle_literal(value: Any, pred_key: str = None, xsd_type_map: dict = None) -> str:
    """Render a Python value as a Turtle literal string.

    Uses the ontology-declared XSD type when xsd_type_map is provided and the
    predicate is known, otherwise falls back to Python type inference.
    """
    xsd_type = _infer_xsd_type(value, pred_key=pred_key, xsd_type_map=xsd_type_map)
    if xsd_type == XSD.boolean or isinstance(value, bool):
        return "true" if value else "false"
    if xsd_type == XSD.integer or isinstance(value, int):
        return f'"{value}"^^<{XSD.integer}>'
    if xsd_type in (XSD.decimal, XSD.float, XSD.double) or isinstance(value, float):
        return f'"{value}"^^<{XSD.decimal}>'
    # For all other declared types (xsd:date, xsd:dateTime, xsd:anyURI, etc.)
    # emit the value as a string with the declared datatype URI
    if xsd_type != XSD.string:
        return f'"{_turtle_escape_string(str(value))}"^^<{xsd_type}>'
    return f'"{_turtle_escape_string(str(value))}"^^<{XSD.string}>'


class KGToRDFConverter:
    """
    Convert extracted LlamaIndex EntityNode / Relation objects to:
      - an rdflib.Graph  (plain entity + relation triples)
      - a Turtle string  (with relation-property annotations per RDF_ANNOTATION_SYNTAX)

    Usage:
        converter = KGToRDFConverter(base_ns="http://example.org/kg/",
                                     onto_ns="http://example.org/ontology#")
        rdf_graph, turtle_annotated = converter.convert(nodes)
        # Pass turtle_annotated to store_rdf_annotations() on RDF store adapters
    """

    def __init__(
        self,
        base_ns: str = DEFAULT_BASE_NS,
        onto_ns: str = DEFAULT_ONTO_NS,
        ontology_manager=None,
    ):
        """
        Args:
            base_ns:           Base namespace for entity instance URIs.
                               e.g. "http://example.org/kg/"
            onto_ns:           Namespace for entity types and relation predicates.
                               e.g. "http://example.org/ontology#"
                               If an ontology_manager is provided and has a base IRI,
                               that is used instead.
            ontology_manager:  Optional OntologyManager — used to resolve the
                               ontology namespace AND to provide the exact URI for
                               every entity/relation label so the round-trip
                               ontology → list → LLM → list → RDF uses the
                               original ontology IRIs rather than a slugify heuristic.
        """
        self._uri_map: Dict[str, str] = {}  # UPPERCASE_NAME -> full URI string
        self._xsd_type_map: Dict[str, str] = {}  # UPPERCASE_PROP_NAME -> XSD URI string
        self._ns_bindings: Dict[str, str] = {}  # prefix -> namespace URI (from ontology)

        if ontology_manager is not None:
            try:
                onto_iri = getattr(ontology_manager, "ontology_iri", None)
                if onto_iri:
                    onto_ns = onto_iri.rstrip("#/") + "#"
            except Exception:
                pass
            # Build exact name→URI lookup from the loaded ontology
            if hasattr(ontology_manager, "get_uri_map"):
                self._uri_map = ontology_manager.get_uri_map()
            # Build xsd type map for datatype properties
            if hasattr(ontology_manager, "get_xsd_type_map"):
                self._xsd_type_map = ontology_manager.get_xsd_type_map()
            # Capture the ontology's own namespace prefix bindings so we can
            # re-bind them in the output graph (produces company:Company not a long URI)
            if hasattr(ontology_manager, "get_namespace_bindings"):
                self._ns_bindings = ontology_manager.get_namespace_bindings()

        self.BASE = Namespace(base_ns.rstrip("/") + "/")
        self.ONTO = Namespace(onto_ns.rstrip("#") + "#")
        self._base_ns = str(self.BASE)
        self._onto_ns = str(self.ONTO)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, nodes: List, annotation_syntax: str = "rdf_1.2") -> Tuple[Graph, str]:
        """
        Convert a list of LlamaIndex nodes (post-extraction).

        Each node carries:
          node.metadata[KG_NODES_KEY]     -> List[EntityNode]
          node.metadata[KG_RELATIONS_KEY] -> List[Relation]

        Args:
            nodes:             LlamaIndex nodes with KG metadata.
            annotation_syntax: How to encode relation properties.
                               ``"rdf_1.2"``     — RDF 1.2 Turtle annotation ``{| |}``
                                                 (recommended, default)
                               ``"rdf_star"``  — Legacy ``<< >> prop value`` lines
                               ``"flat"``      — Plain compound-predicate triples

        Returns:
            (rdf_graph, turtle_str) where:
              - rdf_graph   is an rdflib.Graph with entity + base relation triples
              - turtle_str  is a complete Turtle document including annotations
        """
        from llama_index.core.graph_stores.types import KG_NODES_KEY, KG_RELATIONS_KEY

        g = Graph()
        g.bind("kg", self.BASE)
        g.bind("onto", self.ONTO)
        g.bind("rdf", RDF)
        g.bind("rdfs", RDFS)
        g.bind("xsd", XSD)
        g.bind("owl", OWL)

        # Bind ontology-native prefixes (e.g. company:, foaf:) so the serialised
        # Turtle uses the original ontology namespaces rather than the onto: fallback.
        for prefix, ns_uri in self._ns_bindings.items():
            g.bind(prefix, Namespace(ns_uri))

        # Extra annotation lines appended after rdflib serialization
        annotation_lines: List[str] = []

        # Collect all entities and relations across all nodes.
        # Relations are paired with their source node's ref_doc_id so we can inject it
        # into every annotation block — this is the provenance anchor used by delete_doc().
        all_entities: Dict[str, Any] = {}
        # List of (relation, ref_doc_id) tuples — ref_doc_id may be None for non-incremental ingest
        all_relations: List[Tuple[Any, Optional[str]]] = []

        for node in nodes:
            meta = node.metadata if hasattr(node, "metadata") else {}
            # ref_doc_id can live on the node object directly (LlamaIndex attribute) or in metadata
            ref_doc_id: Optional[str] = (
                getattr(node, "ref_doc_id", None)
                or meta.get("ref_doc_id")
                or meta.get("doc_id")
            )
            for entity in meta.get(KG_NODES_KEY, []):
                if entity.id not in all_entities:
                    all_entities[entity.id] = entity
            for rel in meta.get(KG_RELATIONS_KEY, []):
                all_relations.append((rel, ref_doc_id))

        # Build entity URI lookup and add entity triples
        entity_uris: Dict[str, URIRef] = {}
        for eid, entity in all_entities.items():
            uri = self._entity_uri(entity)
            entity_uris[eid] = uri
            self._add_entity_triples(g, entity, uri)

        # Add relation triples and collect annotation lines.
        # Dedup on (source, label, target) — keep the first ref_doc_id seen so the
        # annotation block always carries a provenance anchor even after dedup.
        seen_relations: Dict[tuple, str] = {}  # rel_key -> ref_doc_id (first seen)
        for relation, ref_doc_id in all_relations:
            rel_key = (relation.source_id, relation.label, relation.target_id)
            if rel_key in seen_relations:
                continue
            seen_relations[rel_key] = ref_doc_id or ""

            subject_uri = entity_uris.get(relation.source_id)
            object_uri = entity_uris.get(relation.target_id)

            if subject_uri is None or object_uri is None:
                logger.debug(
                    "Skipping relation %s: missing entity URI for source=%s or target=%s",
                    relation.label, relation.source_id, relation.target_id,
                )
                continue

            self._add_relation_triples(
                g, relation, subject_uri, object_uri, annotation_lines, annotation_syntax,
                ref_doc_id=ref_doc_id,
            )

        # Serialize base triples to Turtle, then append annotation lines.
        # rdflib only emits @prefix lines for namespaces it actually used while
        # serialising the Graph object.  Annotation lines are appended as raw
        # strings *after* serialisation, so any prefixes used only there
        # (e.g. company: in {| company:role "CTO" |}) would be missing from the
        # header — making the file unparseable by strict Turtle parsers and
        # looking odd when downloaded from GraphDB.
        #
        # Solution: build a canonical prefix block from ALL known bindings
        # (Graph bindings + ontology-native prefixes), strip rdflib's own
        # @prefix header from the serialised output, and prepend ours instead.
        base_turtle = g.serialize(format="turtle")

        if annotation_lines:
            # Collect all @prefix lines rdflib already knows about, then add any
            # ontology-native prefixes it may have omitted (unused in base graph).
            all_bindings: Dict[str, str] = {
                str(p): str(n) for p, n in g.namespaces()
            }
            # Ensure ontology prefixes are present even if not used in base triples
            for prefix, ns_uri in self._ns_bindings.items():
                all_bindings.setdefault(str(prefix), str(ns_uri))

            # Build a sorted prefix block
            prefix_block = "\n".join(
                f"@prefix {p}: <{n}> ."
                for p, n in sorted(all_bindings.items())
                if p  # skip empty/default prefix
            ) + "\n\n"

            # Strip the existing @prefix/@base lines from rdflib's output so we
            # don't duplicate them, then prepend our complete block.
            body_lines = [
                line for line in base_turtle.splitlines()
                if not line.startswith("@prefix") and not line.startswith("@base")
            ]
            body = "\n".join(body_lines).lstrip("\n")
            turtle_out = prefix_block + body + "\n\n" + "\n".join(annotation_lines) + "\n"
        else:
            turtle_out = base_turtle

        annotation_count = len(annotation_lines)
        logger.info(
            "KGToRDFConverter: %d entities, %d relations -> %d RDF triples, "
            "%d annotation lines (syntax=%s)",
            len(all_entities), len(seen_relations), len(g), annotation_count, annotation_syntax,
        )
        return g, turtle_out

    def convert_lc_docs(
        self,
        graph_docs: List,
        annotation_syntax: str = "rdf_1.2",
        source_nodes: Optional[List] = None,
    ) -> Tuple[Graph, str]:
        """Convert LangChain ``GraphDocument`` list directly to RDF.

        Reads LC ``Node`` (id, type, properties) and ``Relationship``
        (source.id, target.id, type, properties) fields natively — no conversion
        to LlamaIndex ``EntityNode`` / ``Relation`` objects.

        source_nodes:
            Optional parallel list of LlamaIndex nodes (same order as graph_docs).
            Used to extract ``ref_doc_id`` provenance metadata.

        Returns ``(rdf_graph, turtle_str)`` — same shape as :meth:`convert`.
        """
        import types as _types

        g = Graph()
        g.bind("kg", self.BASE)
        g.bind("onto", self.ONTO)
        g.bind("rdf", RDF)
        g.bind("rdfs", RDFS)
        g.bind("xsd", XSD)
        g.bind("owl", OWL)
        for prefix, ns_uri in self._ns_bindings.items():
            g.bind(prefix, Namespace(ns_uri))

        annotation_lines: List[str] = []
        all_entities: Dict[str, Any] = {}          # node.id -> LC Node
        all_relations: List[Tuple[Any, Optional[str]]] = []  # (LC Relationship, ref_doc_id)

        for i, graph_doc in enumerate(graph_docs):
            # Resolve ref_doc_id from parallel LI source node or LC source document.
            ref_doc_id: Optional[str] = None
            if source_nodes and i < len(source_nodes):
                li_node = source_nodes[i]
                ref_doc_id = (
                    getattr(li_node, "ref_doc_id", None)
                    or (getattr(li_node, "metadata", None) or {}).get("ref_doc_id")
                    or (getattr(li_node, "metadata", None) or {}).get("doc_id")
                )
            if ref_doc_id is None:
                src = getattr(graph_doc, "source", None)
                if src is not None:
                    src_meta = getattr(src, "metadata", {}) or {}
                    ref_doc_id = src_meta.get("ref_doc_id") or src_meta.get("doc_id")

            for lc_node in getattr(graph_doc, "nodes", []):
                if lc_node.id not in all_entities:
                    all_entities[lc_node.id] = lc_node
            for lc_rel in getattr(graph_doc, "relationships", []):
                all_relations.append((lc_rel, ref_doc_id))

        # Build entity URIs and add entity triples.
        entity_uris: Dict[str, URIRef] = {}
        for eid, lc_node in all_entities.items():
            uri = self.BASE[_slugify(lc_node.id)]
            entity_uris[eid] = uri
            self._add_lc_node_triples(g, lc_node, uri)

        # Add relation triples using a lightweight field-name adapter so
        # _add_relation_triples can be reused without creating LI Relation objects.
        seen_relations: Dict[tuple, str] = {}
        for lc_rel, ref_doc_id in all_relations:
            rel_key = (lc_rel.source.id, lc_rel.type, lc_rel.target.id)
            if rel_key in seen_relations:
                continue
            seen_relations[rel_key] = ref_doc_id or ""

            subject_uri = entity_uris.get(lc_rel.source.id)
            object_uri = entity_uris.get(lc_rel.target.id)
            if subject_uri is None or object_uri is None:
                logger.debug(
                    "Skipping LC relation %s: missing entity URI for source=%s or target=%s",
                    lc_rel.type, lc_rel.source.id, lc_rel.target.id,
                )
                continue

            _rel = _types.SimpleNamespace(
                label=lc_rel.type or "RELATED_TO",
                properties=getattr(lc_rel, "properties", {}) or {},
            )
            self._add_relation_triples(
                g, _rel, subject_uri, object_uri, annotation_lines, annotation_syntax,
                ref_doc_id=ref_doc_id,
            )

        # Serialize — identical logic to convert().
        base_turtle = g.serialize(format="turtle")
        if annotation_lines:
            all_bindings: Dict[str, str] = {str(p): str(n) for p, n in g.namespaces()}
            for prefix, ns_uri in self._ns_bindings.items():
                all_bindings.setdefault(str(prefix), str(ns_uri))
            prefix_block = (
                "\n".join(
                    f"@prefix {p}: <{n}> ."
                    for p, n in sorted(all_bindings.items())
                    if p
                ) + "\n\n"
            )
            body_lines = [
                line for line in base_turtle.splitlines()
                if not line.startswith("@prefix") and not line.startswith("@base")
            ]
            body = "\n".join(body_lines).lstrip("\n")
            turtle_out = prefix_block + body + "\n\n" + "\n".join(annotation_lines) + "\n"
        else:
            turtle_out = base_turtle

        logger.info(
            "KGToRDFConverter (LC): %d entities, %d relations -> %d RDF triples, "
            "%d annotation lines (syntax=%s)",
            len(all_entities), len(seen_relations), len(g), len(annotation_lines), annotation_syntax,
        )
        return g, turtle_out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entity_uri(self, entity) -> URIRef:
        return self.BASE[_slugify(entity.name)]

    def _type_uri(self, label: str) -> URIRef:
        """Resolve an entity type label to its ontology URI.

        If an ontology_manager was provided, looks up the exact URI from the
        ontology (e.g. company:Employee).  Falls back to slugify heuristic
        when no ontology is loaded or the label is not in the ontology.
        """
        key = label.upper()
        if key in self._uri_map:
            return URIRef(self._uri_map[key])
        return self.ONTO[_slugify(label)]

    def _predicate_uri(self, label: str) -> URIRef:
        """Resolve a relation label to its ontology URI.

        Same lookup strategy as _type_uri — exact ontology URI when available,
        slugify heuristic otherwise.
        """
        key = label.upper()
        if key in self._uri_map:
            return URIRef(self._uri_map[key])
        return self.ONTO[_slugify(label)]

    def _add_entity_triples(self, g: Graph, entity, uri: URIRef) -> None:
        """Add rdf:type, rdfs:label, and datatype property triples for an entity."""
        type_uri = self._type_uri(entity.label)
        g.add((uri, RDF.type, type_uri))
        g.add((uri, RDFS.label, Literal(entity.name)))
        for prop_name, prop_value in (entity.properties or {}).items():
            if prop_value is None:
                continue
            pred = self._predicate_uri(prop_name)
            g.add((uri, pred, _make_literal(prop_value, pred_key=prop_name, xsd_type_map=self._xsd_type_map)))

    def _add_lc_node_triples(self, g: Graph, lc_node, uri: URIRef) -> None:
        """Add rdf:type, rdfs:label, and datatype property triples for an LC Node.

        Reads LC ``Node.type`` (label) and ``Node.id`` (name) directly —
        no LlamaIndex EntityNode creation.
        """
        type_uri = self._type_uri(lc_node.type or "Entity")
        g.add((uri, RDF.type, type_uri))
        g.add((uri, RDFS.label, Literal(lc_node.id)))
        for prop_name, prop_value in (getattr(lc_node, "properties", {}) or {}).items():
            if prop_value is None:
                continue
            pred = self._predicate_uri(prop_name)
            g.add((uri, pred, _make_literal(prop_value, pred_key=prop_name, xsd_type_map=self._xsd_type_map)))

    def _add_relation_triples(
        self,
        g: Graph,
        relation,
        subject_uri: URIRef,
        object_uri: URIRef,
        annotation_lines: List[str],
        annotation_syntax: str = "rdf_1.2",
        ref_doc_id: Optional[str] = None,
    ) -> None:
        """Add the base relation triple to g, and encode relation properties.

        ``annotation_syntax="rdf_1.2"`` (RDF 1.2 preferred):
            The base triple is written as an inline annotation block in the
            returned Turtle string:
                <s> <p> <o>
                    {| <prop1> value1 ; <prop2> value2 |} .
            Properties with no values emit a plain triple instead.

        ``annotation_syntax="rdf_star"`` (legacy):
            The base triple is added to g normally, and annotation lines are
            appended as:
                << <s> <p> <o> >>  <prop>  value .

        ``annotation_syntax="flat"`` (SPARQL 1.1 compatible):
            The base triple is added to g normally, and relation properties
            become plain triples on the subject with compound predicates:
                <s>  onto:rel__prop  value .

        In all annotated modes (rdf_1.2, rdf_star), onto:ref_doc_id is always
        injected into the annotation block so that delete_doc() can later find
        and delete these reifier triples by document provenance.
        """
        pred = self._predicate_uri(relation.label)
        # Filter out document-provenance keys — they belong on entity nodes, not
        # on relation reifiers.  Only true edge properties should appear in annotations.
        # Note: LlamaIndex node metadata preserves original key names including spaces
        # (e.g. "modified at" not "modified_at"), so both forms are in _PROVENANCE_KEYS.
        props = {
            k: v for k, v in (relation.properties or {}).items()
            if v is not None and k not in _PROVENANCE_KEYS
        }

        if annotation_syntax == "rdf_1.2" and (props or ref_doc_id):
            # Build inline annotation block — do NOT add plain triple to g so we
            # don't produce a duplicate; the annotation block asserts it.
            prop_parts = []
            # Always inject onto:ref_doc_id first as provenance anchor for delete_doc()
            if ref_doc_id:
                prop_parts.append(
                    f"        <{self.ONTO}ref_doc_id> {_turtle_literal(ref_doc_id)}"
                )
            for prop_name, prop_value in props.items():
                prop_pred = self._predicate_uri(prop_name)
                prop_parts.append(
                    f"        <{prop_pred}> {_turtle_literal(prop_value, pred_key=prop_name, xsd_type_map=self._xsd_type_map)}"
                )
            props_block = " ;\n".join(prop_parts)
            annotation_lines.append(
                f"<{subject_uri}> <{pred}> <{object_uri}>\n"
                f"    {{|\n{props_block}\n    |}} ."
            )
        elif annotation_syntax == "rdf_1.2":
            # No properties and no ref_doc_id — emit plain triple
            g.add((subject_uri, pred, object_uri))
        else:
            # For rdf_star / flat: add the base triple to g normally
            g.add((subject_uri, pred, object_uri))

            if annotation_syntax == "rdf_star":
                # Always inject ref_doc_id first
                if ref_doc_id:
                    annotation_lines.append(
                        f"<< <{subject_uri}> <{pred}> <{object_uri}> >>"
                        f"  <{self.ONTO}ref_doc_id>  {_turtle_literal(ref_doc_id)} ."
                    )
                for prop_name, prop_value in props.items():
                    prop_pred = self._predicate_uri(prop_name)
                    annotation_lines.append(
                        f"<< <{subject_uri}> <{pred}> <{object_uri}> >>"
                        f"  <{prop_pred}>  {_turtle_literal(prop_value, pred_key=prop_name, xsd_type_map=self._xsd_type_map)} ."
                    )
            elif annotation_syntax == "flat":
                for prop_name, prop_value in props.items():
                    flat_pred = self.ONTO[
                        f"{_slugify(relation.label)}__{_slugify(prop_name)}"
                    ]
                    g.add((subject_uri, flat_pred, _make_literal(prop_value, pred_key=prop_name, xsd_type_map=self._xsd_type_map)))


def convert_nodes_to_rdf(
    nodes: List,
    base_ns: str = DEFAULT_BASE_NS,
    onto_ns: str = DEFAULT_ONTO_NS,
    ontology_manager=None,
    annotation_syntax: str = "rdf_1.2",
) -> Tuple[Graph, str]:
    """
    Convenience function: convert extracted nodes to (rdflib.Graph, turtle_str).

    Args:
        nodes:             List of LlamaIndex nodes with KG_NODES_KEY/KG_RELATIONS_KEY
                           metadata (output of _run_kg_extractors_on_nodes).
        base_ns:           Base namespace for entity instance URIs.
        onto_ns:           Namespace for types and predicates.
        ontology_manager:  Optional — used to align type URIs with the loaded ontology.
        annotation_syntax: How to encode relation properties in the output Turtle.
                           ``"rdf_1.2"``    — RDF 1.2 ``{| |}`` inline annotations (default)
                           ``"rdf_star"`` — legacy ``<< >> prop value`` lines
                           ``"flat"``     — plain compound-predicate triples

    Returns:
        (rdf_graph, turtle_str) — pass turtle_str to
        RDFStoreAdapter.store_rdf_annotations() regardless of mode; the adapter
        just POSTs the string as text/turtle.
    """
    converter = KGToRDFConverter(
        base_ns=base_ns,
        onto_ns=onto_ns,
        ontology_manager=ontology_manager,
    )
    return converter.convert(nodes, annotation_syntax=annotation_syntax)
