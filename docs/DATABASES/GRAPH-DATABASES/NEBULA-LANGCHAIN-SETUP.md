# NebulaGraph LangChain Schema Guide

This guide covers the named tags and edge types used when running NebulaGraph with the **LangChain** backend (`GRAPH_BACKEND=langchain`).

> **Note**: As of the v3.8.0 upgrade, **all setup steps in this guide are automated** by
> `_ensure_space_and_schema()` in the adapter code (space creation, `Props__` tag, `Relation__`
> edge, all named entity tags and relationship edge types). You only need to run the steps below
> for manual verification or if you want to use a custom schema.

See [NEBULA-SETUP.md](NEBULA-SETUP.md) for the base infrastructure setup (Docker, `nebula-console` ADD HOSTS, etc.).

## What Is Automatic vs Manual

| Step | Automatic | Manual |
|---|---|---|
| Nebula space creation | **Yes** — `_ensure_space_and_schema()` | Optional verification only |
| `Props__` tag, `Relation__` edge type | **Yes** — `_ensure_space_and_schema()` | Optional verification only |
| Missing columns on `Props__` / `Relation__` | **Yes** — dynamic schema patch adds columns on write | — |
| Named entity tags (`Person`, `Organization`, …) | **Yes** — `_ensure_space_and_schema()` | Optional — steps below for custom schema |
| Named edge types (`WORKS_FOR`, …) | **Yes** — `_ensure_space_and_schema()` | Optional — steps below for custom schema |

**Named tags and edge types are optional pre-creation.** Without them, all vertices fall back to `Props__` and all edges fall back to `Relation__` with a `label` property — ingestion still works. The steps below are useful for verifying the schema or defining a custom one beyond what the adapter creates automatically.

---

## How the LangChain Adapter Uses the Schema

Every ingested entity vertex receives **two tags**:

| Tag | Purpose |
|---|---|
| `Props__` | Universal document metadata (`doc_id`, `ref_doc_id`, `source`, `file_name`, …) on every vertex — required for incremental updates |
| Named entity tag (`Person`, `Organization`, …) | Semantic properties extracted by the LLM (`name`, `hire_date`, `salary`, …) |

Every relationship edge uses a **named edge type** (`WORKS_FOR`, `HAS_DEPARTMENT`, …) when one was pre-created.  If no named type matches the extracted relationship, the edge falls back to `Relation__` with a `label` property.

The adapter discovers what exists at ingest time via `SHOW TAGS` / `SHOW EDGES` — no DDL is issued during ingestion, avoiding NebulaGraph's async schema-propagation delay.

---

## Step 1: Create Entity-Type Tags

Run these in Nebula Studio after selecting the `flexible_graphrag` space from the dropdown.

```nGQL
CREATE TAG IF NOT EXISTS `Person`(
    `id` STRING,
    `name` STRING,
    `hire_date` STRING,
    `date_of_birth` STRING,
    `salary` STRING,
    `title` STRING
);

CREATE TAG IF NOT EXISTS `Organization`(
    `id` STRING,
    `name` STRING,
    `industry` STRING,
    `founded` STRING,
    `description` STRING
);

CREATE TAG IF NOT EXISTS `Company`(
    `id` STRING,
    `name` STRING,
    `industry` STRING,
    `founded` STRING,
    `description` STRING
);

CREATE TAG IF NOT EXISTS `Location`(
    `id` STRING,
    `name` STRING,
    `address` STRING,
    `city` STRING,
    `country` STRING,
    `latitude` STRING,
    `longitude` STRING,
    `capacity` STRING
);

CREATE TAG IF NOT EXISTS `Place`(
    `id` STRING,
    `name` STRING,
    `address` STRING,
    `city` STRING,
    `country` STRING,
    `latitude` STRING,
    `longitude` STRING,
    `capacity` STRING
);

CREATE TAG IF NOT EXISTS `Event`(
    `id` STRING,
    `name` STRING,
    `start_date` STRING,
    `end_date` STRING,
    `date` STRING,
    `description` STRING
);

CREATE TAG IF NOT EXISTS `Product`(
    `id` STRING,
    `name` STRING,
    `description` STRING,
    `category` STRING
);

CREATE TAG IF NOT EXISTS `Department`(
    `id` STRING,
    `name` STRING
);

CREATE TAG IF NOT EXISTS `Project`(
    `id` STRING,
    `name` STRING,
    `status` STRING,
    `description` STRING
);

CREATE TAG IF NOT EXISTS `Technology`(
    `id` STRING,
    `name` STRING,
    `description` STRING
);

CREATE TAG IF NOT EXISTS `Skill`(
    `id` STRING,
    `name` STRING
);

CREATE TAG IF NOT EXISTS `Topic`(
    `id` STRING,
    `name` STRING,
    `description` STRING
);
```

Verify:
```nGQL
SHOW TAGS;
```

---

## Step 2: Create Named Relationship Edge Types

Named edge types allow the LLM to write clean nGQL queries:
```nGQL
MATCH (p:Person)-[:WORKS_FOR]->(c:Organization)
WHERE toLower(id(c)) CONTAINS toLower("acme")
RETURN id(p) AS name
```

Each edge type carries the four most useful document-tracking columns.  Add more columns if needed (see `Relation__` in [NEBULA-SETUP.md](NEBULA-SETUP.md) for the full list).

```nGQL
CREATE EDGE IF NOT EXISTS `WORKS_FOR`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `HAS_DEPARTMENT`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `HAS_LOCATION`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `PART_OF`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `AFFILIATED_WITH`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `MANAGES`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `WORKS_IN_DEPARTMENT`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `ASSIGNED_TO`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `LED_BY`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `ATTENDED_BY`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `HOSTED_BY`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `HELD_AT`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `LOCATED_IN`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `BASED_IN`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `RELATED_TO`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `PRODUCED_BY`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `USES_TECHNOLOGY`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `HAS_SKILL`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `SPONSORS`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
CREATE EDGE IF NOT EXISTS `MENTIONED_IN`(`doc_id` STRING, `ref_doc_id` STRING, `source` STRING, `file_name` STRING);
```

Verify:
```nGQL
SHOW EDGES;
```

**Note**: If your ontology or LLM extraction introduces additional relationship types, add the corresponding `CREATE EDGE IF NOT EXISTS` statement before ingesting.  Any relationship with no matching named edge type falls back to `Relation__` automatically.

---

## Step 3: Ingest

Run ingestion normally.  The adapter calls `SHOW TAGS` and `SHOW EDGES` at the start of each ingest to discover what is available and routes each vertex/edge accordingly.

---

## Querying

Once data is loaded, example nGQL queries for Nebula Studio:

```nGQL
-- All employees of Acme
MATCH (p:Person)-[:WORKS_FOR]->(c:Organization)
WHERE toLower(id(c)) CONTAINS toLower("acme")
RETURN id(p) AS name;

-- All departments at Acme
MATCH (d:Department)-[:PART_OF]->(c:Organization)
WHERE toLower(id(c)) CONTAINS toLower("acme")
RETURN id(d) AS department;

-- Events attended by a person
MATCH (p:Person)-[:ATTENDED_BY]->(e:Event)
WHERE toLower(id(p)) CONTAINS toLower("sarah")
RETURN id(e) AS event;

-- All edges (relationships)
MATCH ()-[e]->() RETURN * LIMIT 50;
```
