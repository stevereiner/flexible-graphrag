# flexible-graphrag/ontology_manager.py

from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import RDF, RDFS, OWL, SKOS
from typing import Dict, List, Set, Literal, Optional
from dataclasses import dataclass
import logging
import os
import re

logger = logging.getLogger(__name__)

@dataclass
class OntologyEntity:
    """Represents an entity type extracted from ontology"""
    name: str  # e.g., "PERSON"
    uri: URIRef
    description: Optional[str] = None
    superclasses: List[str] = None
    properties: Dict[str, str] = None  # property_name -> data_type (e.g., {"salary": "decimal", "hire_date": "dateTime"})
    
    def __hash__(self):
        return hash(self.name)

@dataclass
class OntologyRelation:
    """Represents a relation type extracted from ontology"""
    name: str  # e.g., "WORKS_AT"
    uri: URIRef
    description: Optional[str] = None
    domain: Optional[OntologyEntity] = None
    range: Optional[OntologyEntity] = None
    properties: Dict[str, str] = None  # property_name -> data_type (e.g., {"role": "str", "start_date": "str"})

class OntologyManager:
    """Manages RDF/RDFS/OWL ontologies and schema extraction for PropertyGraphIndex"""
    
    def __init__(self):
        self.graph: Optional[Graph] = None
        self.entities: Dict[str, OntologyEntity] = {}
        self.relations: Dict[str, OntologyRelation] = {}
        self.properties: Dict[str, List[str]] = {}  # entity_type -> [property_names]
        self.relation_properties: Dict[str, List[str]] = {}  # relation_type -> [property_names]
        self.validation_schema: List[tuple] = []  # List of (subject, predicate, object) tuples
    
    def load_ontology(self, source: str, format: str = "turtle") -> None:
        """
        Load RDF/RDFS/OWL ontology from file or URL

        Args:
            source: File path or URL to ontology
            format: "turtle", "rdfxml", "ntriples", "nquads"
        """
        if self.graph is None:
            self.graph = Graph()
        self.graph.parse(source, format=format)
        self._extract_schema()

    def load_ontology_files(self, paths: List[str], format: str = "turtle") -> None:
        """Load and merge multiple ontology files into a single graph.

        Each file is parsed into the same rdflib.Graph so all classes,
        properties, and namespace bindings are visible together.

        Args:
            paths:  List of file paths (or URLs) to ontology files.
            format: Default serialization format; auto-detected from
                    extension (.ttl, .rdf/.owl/.xml, .n3, .nt) when possible.
        """
        _EXT_FORMAT = {
            ".ttl": "turtle",
            ".n3":  "n3",
            ".nt":  "nt",
            ".rdf": "xml",
            ".owl": "xml",
            ".xml": "xml",
        }
        if self.graph is None:
            self.graph = Graph()
        loaded: List[str] = []
        for path in paths:
            ext = os.path.splitext(path)[1].lower()
            fmt = _EXT_FORMAT.get(ext, format)
            try:
                self.graph.parse(path, format=fmt)
                loaded.append(path)
            except Exception as exc:
                logger.warning("OntologyManager: could not load %s (%s) — %s", path, fmt, exc)
        if loaded:
            self._extract_schema()
            logger.info(
                "OntologyManager: loaded %d ontology file(s): %s -> %d entities, %d relations",
                len(loaded),
                ", ".join(os.path.basename(p) for p in loaded),
                len(self.entities),
                len(self.relations),
            )

    def load_ontology_dir(self, directory: str, format: str = "turtle") -> None:
        """Load all ontology files from a directory and merge them.

        Scans *directory* for files with recognised ontology extensions
        (.ttl, .rdf, .owl, .xml, .n3, .nt) and loads them all, sorted
        alphabetically so load order is deterministic.

        Args:
            directory: Path to the directory containing ontology files.
            format:    Fallback format for files whose extension is not
                       recognised.
        """
        _ONTOLOGY_EXTS = {".ttl", ".rdf", ".owl", ".xml", ".n3", ".nt"}
        if not os.path.isdir(directory):
            logger.warning("OntologyManager: ontology directory not found: %s", directory)
            return
        paths = sorted(
            os.path.join(directory, fname)
            for fname in os.listdir(directory)
            if os.path.splitext(fname)[1].lower() in _ONTOLOGY_EXTS
        )
        if not paths:
            logger.warning("OntologyManager: no ontology files found in %s", directory)
            return
        self.load_ontology_files(paths, format=format)

    def load_ontology_from_content(self, content: bytes, format: str = "turtle") -> None:
        """Load ontology from in-memory content"""
        self.graph = Graph()
        self.graph.parse(data=content.decode("utf-8"), format=format)
        self._extract_schema()
    
    def load_ontology_from_sparql(self, endpoint_url: str) -> None:
        """Load ontology schema from SPARQL endpoint"""
        # Implementation can reuse SPARQLOntologyLoader below
        pass
    
    def _extract_schema(self) -> None:
        """Extract entity types and relations from RDF/RDFS/OWL ontology"""
        
        # Extract OWL Classes (Entity Types)
        class_query = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?cls ?label ?comment WHERE {
            ?cls a owl:Class .
            OPTIONAL { ?cls rdfs:label ?label }
            OPTIONAL { ?cls rdfs:comment ?comment }
        }
        """
        
        for row in self.graph.query(class_query):
            class_name = self._uri_to_name(row.cls)
            self.entities[class_name] = OntologyEntity(
                name=class_name,
                uri=row.cls,
                description=str(row.comment) if row.comment else None,
                properties={}  # Will be populated by datatype properties
            )
        
        # Extract OWL DatatypeProperties (Entity Properties AND Relation Properties)
        datatype_property_query = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        SELECT DISTINCT ?prop ?label ?domain ?range WHERE {
            ?prop a owl:DatatypeProperty .
            OPTIONAL { ?prop rdfs:label ?label }
            OPTIONAL { ?prop rdfs:domain ?domain }
            OPTIONAL { ?prop rdfs:range ?range }
        }
        """
        
        for row in self.graph.query(datatype_property_query):
            prop_name = self._uri_to_name(row.prop)
            domain_name = self._uri_to_name(row.domain) if row.domain else None
            
            # Extract XSD type from range
            prop_type = "string"  # Default
            if row.range:
                range_str = str(row.range)
                if "decimal" in range_str or "float" in range_str or "double" in range_str:
                    prop_type = "float"
                elif "integer" in range_str or "int" in range_str:
                    prop_type = "int"
                elif "boolean" in range_str:
                    prop_type = "bool"
                elif "dateTime" in range_str or "date" in range_str:
                    prop_type = "str"  # Treat dates as strings for now
            
            # Determine if this is an entity property or relation property
            # Entity properties have an entity (owl:Class) as domain
            # Relation properties have a relation (owl:ObjectProperty) as domain
            if domain_name:
                # Check if domain is an entity
                if domain_name in self.entities:
                    self.entities[domain_name].properties[prop_name] = prop_type
                    
                    # Also track in global properties dict for easy lookup
                    if domain_name not in self.properties:
                        self.properties[domain_name] = []
                    self.properties[domain_name].append(prop_name)
                else:
                    # Domain might be a relation - store temporarily, will associate after relations are loaded
                    # We'll do a second pass after relations are extracted
                    if not hasattr(self, '_pending_relation_props'):
                        self._pending_relation_props = []
                    self._pending_relation_props.append((domain_name, prop_name, prop_type))
        
        # Extract OWL Object Properties (Relation Types)
        property_query = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?prop ?label ?domain ?range WHERE {
            ?prop a owl:ObjectProperty .
            OPTIONAL { ?prop rdfs:label ?label }
            OPTIONAL { ?prop rdfs:domain ?domain }
            OPTIONAL { ?prop rdfs:range ?range }
        }
        """
        
        for row in self.graph.query(property_query):
            prop_name = self._uri_to_name(row.prop)
            domain_name = self._uri_to_name(row.domain) if row.domain else None
            range_name = self._uri_to_name(row.range) if row.range else None
            
            self.relations[prop_name] = OntologyRelation(
                name=prop_name,
                uri=row.prop,
                domain=self.entities.get(domain_name) if domain_name else None,
                range=self.entities.get(range_name) if range_name else None,
                properties={}  # Will be populated with relation properties
            )
        
        # Second pass: Associate pending relation properties with their relations
        if hasattr(self, '_pending_relation_props'):
            for domain_name, prop_name, prop_type in self._pending_relation_props:
                if domain_name in self.relations:
                    self.relations[domain_name].properties[prop_name] = prop_type
                    
                    # Track in global relation_properties dict
                    if domain_name not in self.relation_properties:
                        self.relation_properties[domain_name] = []
                    self.relation_properties[domain_name].append(prop_name)
            delattr(self, '_pending_relation_props')
        
        # Build validation schema (which entity types can connect via which relations)
        self._build_validation_schema()
    
    def _build_validation_schema(self) -> None:
        """Build validation schema from domain/range constraints"""
        for rel_name, relation in self.relations.items():
            if relation.domain and relation.range:
                # Create triplet: (domain, relation, range)
                triplet = (relation.domain.name, rel_name, relation.range.name)
                self.validation_schema.append(triplet)
            elif relation.domain:
                # If only domain is specified, allow any range
                # Add triplets for all possible entity types
                for entity_name in self.entities.keys():
                    triplet = (relation.domain.name, rel_name, entity_name)
                    self.validation_schema.append(triplet)
    
    def _uri_to_name(self, uri: Optional[URIRef]) -> Optional[str]:
        """Convert URI to entity/relation name"""
        if uri is None:
            return None
        uri_str = str(uri)
        # Extract local name from URI (after # or /)
        name = uri_str.split('#')[-1].split('/')[-1]
        return name.upper()
    
    def get_entities_literal(self):
        """Get entity types as tuple for SchemaLLMPathExtractor"""
        return tuple(self.entities.keys())
    
    def get_relations_literal(self):
        """Get relation types as tuple for SchemaLLMPathExtractor"""
        return tuple(self.relations.keys())
    
    def get_validation_schema(self) -> List[tuple]:
        """Get validation schema for SchemaLLMPathExtractor"""
        return self.validation_schema
    
    def get_uri_map(self) -> Dict[str, str]:
        """Return a name->URI string dict for all entities and relations.

        Used by KGToRDFConverter to map LLM-produced label strings back to
        their exact ontology URIs, closing the round-trip without heuristics.

        Keys are the uppercased local names produced by _uri_to_name() — the
        same strings that SchemaLLMPathExtractor sees as possible_entities /
        possible_relations.  Values are the full URI strings from the ontology.

        Example (company_ontology.ttl):
            {
              "EMPLOYEE":   "http://example.org/company/Employee",
              "COMPANY":    "http://example.org/company/Company",
              "EMPLOYS":    "http://example.org/company/employs",
              "WORKS_FOR":  "http://example.org/company/works_for",
              ...
            }
        """
        uri_map: Dict[str, str] = {}
        for name, entity in self.entities.items():
            uri_map[name] = str(entity.uri)
        for name, relation in self.relations.items():
            uri_map[name] = str(relation.uri)
        # Also include DatatypeProperties so annotation property predicates
        # (e.g. company:assignment_percentage, company:salary) resolve to their
        # exact ontology URIs rather than falling back to the onto: namespace.
        if self.graph is not None:
            datatype_prop_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?prop WHERE { ?prop a owl:DatatypeProperty . }
            """
            for row in self.graph.query(datatype_prop_query):
                name = self._uri_to_name(row.prop)
                if name:
                    uri_map[name] = str(row.prop)
        return uri_map

    def get_namespace_bindings(self) -> Dict[str, str]:
        """Return the namespace prefix bindings from the loaded ontology graph.

        Used by KGToRDFConverter to bind the original ontology prefixes in the
        output Turtle, so serialisation produces ``company:Company`` instead of
        ``<http://example.org/company/Company>``.

        Returns a dict of {prefix: namespace_uri_string}, e.g.::

            {"company": "http://example.org/company/",
             "foaf":    "http://xmlns.com/foaf/0.1/"}

        Standard prefixes (rdf, rdfs, owl, xsd) are excluded — rdflib always
        binds those automatically.
        """
        _STANDARD = {"rdf", "rdfs", "owl", "xsd", "xml", ""}
        if self.graph is None:
            return {}
        return {
            str(prefix): str(ns)
            for prefix, ns in self.graph.namespaces()
            if str(prefix) not in _STANDARD
        }

    def get_xsd_type_map(self) -> Dict[str, str]:
        """Return a prop_name -> XSD datatype URI dict for all datatype properties.

        Used by KGToRDFConverter._make_literal() / _turtle_literal() to emit
        correctly typed literals (e.g. "2008-09-10"^^xsd:date) instead of
        always falling back to xsd:string.

        Keys are the uppercased local names of OWL DatatypeProperties.
        Values are full XSD datatype URI strings.

        Example:
            {
              "SALARY":     "http://www.w3.org/2001/XMLSchema#decimal",
              "HIRE_DATE":  "http://www.w3.org/2001/XMLSchema#date",
              "AGE":        "http://www.w3.org/2001/XMLSchema#integer",
              "IS_ACTIVE":  "http://www.w3.org/2001/XMLSchema#boolean",
            }
        """
        _PY_TO_XSD = {
            "float":   "http://www.w3.org/2001/XMLSchema#decimal",
            "int":     "http://www.w3.org/2001/XMLSchema#integer",
            "bool":    "http://www.w3.org/2001/XMLSchema#boolean",
            "string":  "http://www.w3.org/2001/XMLSchema#string",
            "str":     "http://www.w3.org/2001/XMLSchema#string",
        }
        xsd_map: Dict[str, str] = {}
        # Primary source: rdfs:range declared on owl:DatatypeProperty in the ontology graph.
        # This is authoritative and covers relation-property annotations (e.g. assignment_percentage)
        # that are not inside any entity/relation .properties dict.
        if self.graph is not None:
            datatype_range_query = """
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?prop ?range WHERE {
                ?prop a owl:DatatypeProperty .
                OPTIONAL { ?prop rdfs:range ?range . }
            }
            """
            for row in self.graph.query(datatype_range_query):
                name = self._uri_to_name(row.prop)
                if name:
                    range_uri = str(row.range) if row.range else "http://www.w3.org/2001/XMLSchema#string"
                    xsd_map[name] = range_uri
        # Fallback / override: YAML-style entity/relation .properties dicts (Python type names).
        for entity in self.entities.values():
            for prop_name, prop_type in (entity.properties or {}).items():
                key = prop_name.upper()
                if key not in xsd_map:
                    xsd_map[key] = _PY_TO_XSD.get(prop_type, "http://www.w3.org/2001/XMLSchema#string")
        for relation in self.relations.values():
            for prop_name, prop_type in (relation.properties or {}).items():
                key = prop_name.upper()
                if key not in xsd_map:
                    xsd_map[key] = _PY_TO_XSD.get(prop_type, "http://www.w3.org/2001/XMLSchema#string")
        return xsd_map

    def get_entity_properties(self, entity_name: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """
        Get properties for entity types.
        
        Args:
            entity_name: Specific entity to get properties for, or None for all
            
        Returns:
            Dict mapping entity names to their properties (property_name -> type)
        """
        if entity_name:
            entity = self.entities.get(entity_name)
            return {entity_name: entity.properties} if entity and entity.properties else {}
        
        # Return all entity properties
        return {name: entity.properties for name, entity in self.entities.items() if entity.properties}
    
    def get_relation_properties(self, relation_name: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """
        Get properties for relation types.
        
        Args:
            relation_name: Specific relation to get properties for, or None for all
            
        Returns:
            Dict mapping relation names to their properties (property_name -> type)
        """
        if relation_name:
            relation = self.relations.get(relation_name)
            return {relation_name: relation.properties} if relation and relation.properties else {}
        
        # Return all relation properties
        return {name: relation.properties for name, relation in self.relations.items() if relation.properties}
    
    def export_schema_json(self, filepath: str) -> None:
        """Export extracted schema as JSON for documentation"""
        import json
        schema = {
            "entities": {
                name: {
                    "uri": str(entity.uri),
                    "description": entity.description,
                    "properties": entity.properties if entity.properties else {}
                }
                for name, entity in self.entities.items()
            },
            "relations": {
                name: {
                    "uri": str(relation.uri),
                    "domain": relation.domain.name if relation.domain else None,
                    "range": relation.range.name if relation.range else None,
                    "properties": relation.properties if relation.properties else {}
                }
                for name, relation in self.relations.items()
            },
            "validation_schema": self.validation_schema
        }
        with open(filepath, 'w') as f:
            json.dump(schema, f, indent=2)
