
***

## 3. `ontology_examples_and_config.md`

```markdown
# RDF Ontology Examples & Configuration for flexible-graphrag

## Example 1: FOAF (Friend-of-a-Friend) Ontology

**File**: `schemas/foaf_ontology.ttl`

```turtle
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

# Define classes (entity types)
foaf:Person a owl:Class ;
    rdfs:label "Person" ;
    rdfs:comment "A human being" .

foaf:Organization a owl:Class ;
    rdfs:label "Organization" ;
    rdfs:comment "A collective entity" .

foaf:Project a owl:Class ;
    rdfs:label "Project" ;
    rdfs:comment "A project or initiative" .

# Define properties (relation types)
foaf:name a owl:DatatypeProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range rdfs:Literal ;
    rdfs:label "name" .

foaf:workplaceHomepage a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range foaf:Organization ;
    rdfs:label "workplaceHomepage" ;
    rdfs:comment "Person works at Organization" .

foaf:knows a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range foaf:Person ;
    rdfs:label "knows" .

foaf:topic_interest a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range foaf:Project ;
    rdfs:label "topic_interest" .

foaf:member a owl:ObjectProperty ;
    rdfs:domain foaf:Person ;
    rdfs:range foaf:Organization ;
    rdfs:label "member" .
