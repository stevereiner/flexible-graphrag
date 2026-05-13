# RDF Ontology Examples and Configuration

This page covers how to enable ontology-guided KG extraction and provides example ontology files in Turtle format.

---

## Enabling ontologies

Add these variables to your `.env` file:

```env
# Enable ontology-guided extraction
USE_ONTOLOGY=true

# Choose one of the three path options below:

# Single ontology file
ONTOLOGY_PATH=./rdf/schemas/my_ontology.ttl

# Multiple ontology files (comma-separated)
ONTOLOGY_PATHS=./rdf/schemas/company_classes.ttl,./rdf/schemas/company_properties.ttl,./rdf/schemas/common_ontology.ttl

# Directory of ontology files (loads all .ttl files in the directory)
ONTOLOGY_DIR=./rdf/schemas/
```

`ONTOLOGY_PATHS` takes precedence over `ONTOLOGY_PATH`; `ONTOLOGY_DIR` is used when neither is set.

```env
# Ontology format (auto-detected from extension; set explicitly if needed)
ONTOLOGY_FORMAT=turtle          # turtle | rdfxml | ntriples | nquads

# Schema strictness
STRICT_SCHEMA_VALIDATION=false  # false (default) = ontology guides but LLM can go beyond it
                                 # true = only extract types explicitly defined in the ontology
```

Set `RDF_GRAPH_DB` to also write extracted triples to an RDF triple store alongside the property graph:

```env
RDF_GRAPH_DB=fuseki     # fuseki | graphdb | oxigraph | none (default)
```

See [Configure RDF Graph Databases](../../CONFIGURATION/CONFIG-RDF-STORES.md) for full RDF store connection settings.

---

## Example 1: FOAF ontology

A standard vocabulary for people and organizations.

**File**: `rdf/schemas/foaf_ontology.ttl`

```turtle
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .

# Classes (entity types)
foaf:Person a owl:Class ;
    rdfs:label "Person" ;
    rdfs:comment "A human being" .

foaf:Organization a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A collective entity" .

foaf:Project a owl:Class ;
    rdfs:label "Project" ;
    rdfs:comment "A project or initiative" .

# Properties (relation types)
foaf:name a owl:DatatypeProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range  rdfs:Literal ;
    rdfs:label  "name" .

foaf:workplaceHomepage a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range  foaf:Organization ;
    rdfs:label  "workplaceHomepage" ;
    rdfs:comment "Person works at Organization" .

foaf:knows a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range  foaf:Person ;
    rdfs:label  "knows" .

foaf:topic_interest a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range  foaf:Project ;
    rdfs:label  "topic_interest" .

foaf:member a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range  foaf:Organization ;
    rdfs:label  "member" .
```

**`.env` setup for this ontology:**

```env
USE_ONTOLOGY=true
ONTOLOGY_PATH=./rdf/schemas/foaf_ontology.ttl
```

---

## Example 2: Company ontology (multi-file)

The built-in company ontology included with Flexible GraphRAG splits classes and properties into separate files.

**Classes file** — `rdf/schemas/company_classes.ttl`:

```turtle
@prefix company: <http://example.org/company/> .
@prefix common:  <https://integratedsemantics.org/flexible-graphrag/common#> .
@prefix owl:     <http://www.w3.org/2002/07/owl#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .

company:Employee a owl:Class ;
    rdfs:subClassOf common:Person ;
    rdfs:label "Employee" .

company:Department a owl:Class ;
    rdfs:label "Department" .

company:Company a owl:Class ;
    rdfs:label "Company" .

company:Project a owl:Class ;
    rdfs:label "Project" .

company:works_for a owl:ObjectProperty ;
    rdfs:domain common:Person ;
    rdfs:range  company:Company ;
    rdfs:label  "works_for" .

company:part_of a owl:ObjectProperty ;
    rdfs:domain company:Department ;
    rdfs:range  company:Company ;
    rdfs:label  "part_of" .
```

**`.env` setup for multi-file company ontology:**

```env
USE_ONTOLOGY=true
ONTOLOGY_PATHS=./rdf/schemas/company_classes.ttl,./rdf/schemas/company_properties.ttl,./rdf/schemas/common_ontology.ttl
```

---

## Example 3: Custom domain ontology

A minimal template for any domain.

**File**: `rdf/schemas/my_domain.ttl`

```turtle
@prefix my:   <https://example.org/my-domain/> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

# --- Classes ---

my:Product a owl:Class ;
    rdfs:label "Product" .

my:Supplier a owl:Class ;
    rdfs:label "Supplier" .

my:Category a owl:Class ;
    rdfs:label "Category" .

# --- Object properties (entity → entity) ---

my:supplied_by a owl:ObjectProperty ;
    rdfs:domain my:Product ;
    rdfs:range  my:Supplier ;
    rdfs:label  "supplied_by" .

my:belongs_to a owl:ObjectProperty ;
    rdfs:domain my:Product ;
    rdfs:range  my:Category ;
    rdfs:label  "belongs_to" .

# --- Datatype properties (entity → literal) ---

my:sku a owl:DatatypeProperty ;
    rdfs:domain my:Product ;
    rdfs:range  xsd:string ;
    rdfs:label  "sku" .

my:unit_price a owl:DatatypeProperty ;
    rdfs:domain my:Product ;
    rdfs:range  xsd:decimal ;
    rdfs:label  "unit_price" .
```

**`.env` setup:**

```env
USE_ONTOLOGY=true
ONTOLOGY_PATH=./rdf/schemas/my_domain.ttl
STRICT_SCHEMA_VALIDATION=false
```

---

## Related pages

- [Configure RDF Graph Databases](../../CONFIGURATION/CONFIG-RDF-STORES.md) — store connection settings, storage modes
- [RDF and ontology support](RDF-ONTOLOGY-SUPPORT.md) — architecture, full environment variable reference
- [RDF store user guide](RDF-STORE-USER-GUIDE.md) — dashboard exploration, SPARQL queries, incremental sync
