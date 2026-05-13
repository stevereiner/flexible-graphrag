"""
rdf_cleanup.py — RDF store cleanup utility for Flexible GraphRAG

Provides commands to clear RDF data without recreating Docker volumes.
Run from the project root with the venv active:

    python scripts/rdf_cleanup.py --help
    python scripts/rdf_cleanup.py clear-all
    python scripts/rdf_cleanup.py clear-doc <ref_doc_id>
    python scripts/rdf_cleanup.py list-docs

Reads store connection from the same .env / environment variables as the
main application.
"""

import argparse
import os
import sys

# Allow importing from flexible-graphrag package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flexible-graphrag"))

import requests


# ---------------------------------------------------------------------------
# Config (read from env, same vars as the main app)
# ---------------------------------------------------------------------------

GRAPH_URI = os.environ.get(
    "RDF_BASE_NAMESPACE", "https://integratedsemantics.org/flexible-graphrag/kg/"
).rstrip("/")

ONTO_NS = "https://integratedsemantics.org/flexible-graphrag/ontology#"

# Fuseki
FUSEKI_URL     = os.environ.get("FUSEKI_BASE_URL", "http://localhost:3030")
FUSEKI_DATASET = os.environ.get("FUSEKI_DATASET",  "flexible-graphrag")
FUSEKI_USER    = os.environ.get("FUSEKI_USERNAME",  "admin")
FUSEKI_PASS    = os.environ.get("FUSEKI_PASSWORD",  "admin")

# GraphDB
GRAPHDB_URL  = os.environ.get("GRAPHDB_BASE_URL",    "http://localhost:7200")
GRAPHDB_REPO = os.environ.get("GRAPHDB_REPOSITORY",  "flexible-graphrag")
GRAPHDB_USER = os.environ.get("GRAPHDB_USERNAME",    "admin")
GRAPHDB_PASS = os.environ.get("GRAPHDB_PASSWORD",    "admin")

# Oxigraph
OXIGRAPH_URL = os.environ.get("OXIGRAPH_URL", "http://localhost:7878")

# Amazon Neptune RDF/SPARQL
NEPTUNE_RDF_HOST     = os.environ.get("NEPTUNE_RDF_HOST", "")
NEPTUNE_RDF_PORT     = int(os.environ.get("NEPTUNE_RDF_PORT", "8182"))
NEPTUNE_RDF_REGION   = os.environ.get("NEPTUNE_RDF_REGION", "us-east-1")
NEPTUNE_RDF_USE_HTTPS = os.environ.get("NEPTUNE_RDF_USE_HTTPS", "true").lower() == "true"
NEPTUNE_RDF_USE_IAM  = os.environ.get("NEPTUNE_RDF_USE_IAM_AUTH", "true").lower() == "true"
NEPTUNE_RDF_KEY_ID   = os.environ.get("NEPTUNE_RDF_AWS_ACCESS_KEY_ID", "") or os.environ.get("AWS_ACCESS_KEY_ID", "")
NEPTUNE_RDF_SECRET   = os.environ.get("NEPTUNE_RDF_AWS_SECRET_ACCESS_KEY", "") or os.environ.get("AWS_SECRET_ACCESS_KEY", "")


# ---------------------------------------------------------------------------
# SPARQL helpers
# ---------------------------------------------------------------------------

def _fuseki_ensure_dataset() -> None:
    """Create the Fuseki dataset via the admin API if it does not already exist."""
    admin_url = f"{FUSEKI_URL}/$/datasets"
    auth = (FUSEKI_USER, FUSEKI_PASS) if FUSEKI_USER else None
    resp = requests.get(f"{admin_url}/{FUSEKI_DATASET}", auth=auth, timeout=10)
    if resp.status_code == 200:
        return
    # Dataset missing — create a persistent TDB2 dataset
    resp = requests.post(
        admin_url,
        data={"dbName": FUSEKI_DATASET, "dbType": "tdb2"},
        auth=auth,
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Could not create Fuseki dataset '{FUSEKI_DATASET}': "
            f"{resp.status_code} {resp.text}"
        )


def _fuseki_update(sparql: str) -> None:
    _fuseki_ensure_dataset()
    url  = f"{FUSEKI_URL}/{FUSEKI_DATASET}/update"
    auth = (FUSEKI_USER, FUSEKI_PASS) if FUSEKI_USER else None
    # Send as raw application/sparql-update body — the stain/jena-fuseki image
    # auto-creates datasets that accept this but not always form-encoded POST.
    # Fall back to form-encoded if the raw body returns 405.
    r = requests.post(
        url,
        data=sparql.encode("utf-8"),
        headers={"Content-Type": "application/sparql-update"},
        auth=auth,
        timeout=60,
    )
    if r.status_code == 405:
        r = requests.post(url, data={"update": sparql}, auth=auth, timeout=60)
    r.raise_for_status()


def _fuseki_graph_exists(graph_uri: str) -> bool:
    """Return True if the named graph exists and has at least one triple."""
    query = f"ASK {{ GRAPH <{graph_uri}> {{ ?s ?p ?o }} }}"
    try:
        url  = f"{FUSEKI_URL}/{FUSEKI_DATASET}/sparql"
        auth = (FUSEKI_USER, FUSEKI_PASS) if FUSEKI_USER else None
        r = requests.post(url, data={"query": query},
                          headers={"Accept": "application/sparql-results+json"},
                          auth=auth, timeout=10)
        r.raise_for_status()
        return r.json().get("boolean", False)
    except Exception:
        return False


def _fuseki_clear_graph(graph_uri: str) -> None:
    """Clear a named graph in Fuseki, skipping silently if it does not exist."""
    if not _fuseki_graph_exists(graph_uri):
        print(f"  [fuseki] graph does not exist yet - nothing to clear")
        return
    _fuseki_update(f"CLEAR GRAPH <{graph_uri}>")


def _fuseki_select(sparql: str) -> list:
    url  = f"{FUSEKI_URL}/{FUSEKI_DATASET}/sparql"
    auth = (FUSEKI_USER, FUSEKI_PASS) if FUSEKI_USER else None
    r = requests.post(url, data={"query": sparql},
                      headers={"Accept": "application/sparql-results+json"},
                      auth=auth, timeout=60)
    r.raise_for_status()
    return r.json().get("results", {}).get("bindings", [])


def _graphdb_update(sparql: str) -> None:
    url  = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}/statements"
    auth = (GRAPHDB_USER, GRAPHDB_PASS) if GRAPHDB_USER else None
    r = requests.post(url, data={"update": sparql}, auth=auth, timeout=60)
    r.raise_for_status()


def _graphdb_select(sparql: str) -> list:
    url  = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
    auth = (GRAPHDB_USER, GRAPHDB_PASS) if GRAPHDB_USER else None
    r = requests.post(url, data={"query": sparql},
                      headers={"Accept": "application/sparql-results+json"},
                      auth=auth, timeout=60)
    r.raise_for_status()
    return r.json().get("results", {}).get("bindings", [])


def _oxigraph_update(sparql: str) -> None:
    r = requests.post(f"{OXIGRAPH_URL}/update", data={"update": sparql}, timeout=60)
    r.raise_for_status()


def _oxigraph_clear_graph(graph_uri: str) -> None:
    """Clear a named graph in Oxigraph via REST (DELETE /store?graph=<uri>).

    Oxigraph does not support CLEAR GRAPH in its SPARQL Update implementation;
    the Graph Store HTTP Protocol DELETE endpoint is the correct approach.
    """
    r = requests.delete(f"{OXIGRAPH_URL}/store", params={"graph": graph_uri}, timeout=60)
    # 404 means graph didn't exist — that's fine
    if r.status_code != 404:
        r.raise_for_status()


def _oxigraph_select(sparql: str) -> list:
    r = requests.get(f"{OXIGRAPH_URL}/query", params={"query": sparql},
                     headers={"Accept": "application/sparql-results+json"}, timeout=30)
    r.raise_for_status()
    return r.json().get("results", {}).get("bindings", [])


def _neptune_rdf_signed_headers(method: str, url: str, data: dict) -> dict:
    """Build SigV4-signed headers for a Neptune SPARQL request."""
    from types import SimpleNamespace
    from botocore.awsrequest import AWSRequest
    from botocore.auth import SigV4Auth
    import json as _json

    creds = SimpleNamespace(
        access_key=NEPTUNE_RDF_KEY_ID,
        secret_key=NEPTUNE_RDF_SECRET,
        token=None,
        region=NEPTUNE_RDF_REGION,
    )
    req = AWSRequest(method=method, url=url, data=data)
    SigV4Auth(creds, "neptune-db", NEPTUNE_RDF_REGION).add_auth(req)  # type: ignore[arg-type]
    headers = dict(req.headers)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    return headers


def _neptune_rdf_endpoint() -> str:
    protocol = "https" if NEPTUNE_RDF_USE_HTTPS else "http"
    return f"{protocol}://{NEPTUNE_RDF_HOST}:{NEPTUNE_RDF_PORT}/sparql"


def _neptune_rdf_update(sparql: str) -> None:
    url = _neptune_rdf_endpoint()
    data = {"update": sparql}
    headers = _neptune_rdf_signed_headers("POST", url, data) if NEPTUNE_RDF_USE_IAM else {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    r = requests.post(url, data=data, headers=headers, timeout=60)
    r.raise_for_status()


def _neptune_rdf_select(sparql: str) -> list:
    url = _neptune_rdf_endpoint()
    data = {"query": sparql}
    headers = _neptune_rdf_signed_headers("POST", url, data) if NEPTUNE_RDF_USE_IAM else {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    headers["Accept"] = "application/sparql-results+json"
    r = requests.post(url, data=data, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json().get("results", {}).get("bindings", [])


def _neptune_rdf_clear_graph(graph_uri: str) -> None:
    """Neptune supports SPARQL CLEAR GRAPH."""
    _neptune_rdf_update(f"CLEAR GRAPH <{graph_uri}>")


# ---------------------------------------------------------------------------
# SPARQL query/update builders
# ---------------------------------------------------------------------------

def _clear_all_query(graph_uri: str) -> str:
    return f"CLEAR GRAPH <{graph_uri}>"


def _clear_doc_query(ref_doc_id: str, graph_uri: str) -> str:
    escaped = ref_doc_id.replace("\\", "\\\\").replace('"', '\\"')
    return f"""PREFIX onto: <{ONTO_NS}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

DELETE {{ GRAPH <{graph_uri}> {{ ?s ?p ?o }} }}
WHERE  {{ GRAPH <{graph_uri}> {{ ?s ?p ?o ; onto:ref_doc_id "{escaped}" }} }} ;

DELETE {{ GRAPH <{graph_uri}> {{ ?reifier ?rp ?ro }} }}
WHERE  {{
  GRAPH <{graph_uri}> {{
    ?reifier onto:ref_doc_id "{escaped}" .
    ?reifier ?rp ?ro .
    FILTER(isBlank(?reifier) || (isIRI(?reifier) && STRSTARTS(STR(?reifier), "urn:")))
  }}
}}
"""


def _list_docs_query(graph_uri: str) -> str:
    return f"""
PREFIX onto: <{ONTO_NS}>
SELECT DISTINCT ?ref_doc_id ?file_name ?file_path (COUNT(?s) AS ?triples)
WHERE {{
  GRAPH <{graph_uri}> {{
    ?s onto:ref_doc_id ?ref_doc_id .
    OPTIONAL {{ ?s onto:file_name ?file_name }}
    OPTIONAL {{ ?s onto:file_path ?file_path }}
  }}
}}
GROUP BY ?ref_doc_id ?file_name ?file_path
ORDER BY ?file_name
"""


def _count_query(graph_uri: str) -> str:
    return f"""
SELECT (COUNT(*) AS ?count)
WHERE {{ GRAPH <{graph_uri}> {{ ?s ?p ?o }} }}
"""


# ---------------------------------------------------------------------------
# Store actions
# ---------------------------------------------------------------------------

STORES = {
    "fuseki":      {"update": _fuseki_update,       "select": _fuseki_select,       "clear": _fuseki_clear_graph},
    "graphdb":     {"update": _graphdb_update,      "select": _graphdb_select,      "clear": None},
    "oxigraph":    {"update": _oxigraph_update,     "select": _oxigraph_select,     "clear": _oxigraph_clear_graph},
    "neptune_rdf": {"update": _neptune_rdf_update,  "select": _neptune_rdf_select,  "clear": _neptune_rdf_clear_graph},
}


def _run_on_stores(enabled: list, action: str, sparql_fn, *args) -> None:
    for store in enabled:
        fn = STORES[store][action]
        try:
            result = fn(sparql_fn(*args))
            if action == "select":
                print(f"\n  [{store}]")
                if not result:
                    print("    (no results)")
                for row in result:
                    vals = {k: v["value"] for k, v in row.items()}
                    print("   ", vals)
            else:
                print(f"  [{store}] OK")
        except Exception as e:
            print(f"  [{store}] ERROR: {e}")


def _enabled_stores(args) -> list:
    all_stores = ("fuseki", "graphdb", "oxigraph", "neptune_rdf")
    explicit = [s for s in all_stores if getattr(args, s, False)]
    if explicit:
        return explicit
    # Auto-detect from RDF_GRAPH_DB (modern single-store picker)
    rdf_graph_db = os.environ.get("RDF_GRAPH_DB", "none").lower().strip()
    if rdf_graph_db in all_stores:
        return [rdf_graph_db]
    # Legacy multi-store flags (FUSEKI_ENABLED=true etc.)
    detected = []
    if os.environ.get("FUSEKI_ENABLED", "").lower() == "true":
        detected.append("fuseki")
    if os.environ.get("GRAPHDB_ENABLED", "").lower() == "true":
        detected.append("graphdb")
    if os.environ.get("OXIGRAPH_ENABLED", "").lower() == "true":
        detected.append("oxigraph")
    if not detected:
        print("No RDF stores enabled in .env. Use --fuseki / --graphdb / --oxigraph / --neptune-rdf to specify one explicitly.")
        sys.exit(0)
    return detected


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_list_docs(args) -> None:
    """List all ingested documents and their triple counts."""
    stores = _enabled_stores(args)
    print(f"\nDocuments in graph <{GRAPH_URI}>:")
    _run_on_stores(stores, "select", _list_docs_query, GRAPH_URI)


def cmd_count(args) -> None:
    """Count total triples in the named graph."""
    stores = _enabled_stores(args)
    print(f"\nTriple counts for graph <{GRAPH_URI}>:")
    _run_on_stores(stores, "select", _count_query, GRAPH_URI)


def cmd_clear_doc(args) -> None:
    """Delete all triples for a specific ref_doc_id."""
    stores = _enabled_stores(args)
    print(f"\nDeleting triples for ref_doc_id='{args.ref_doc_id}' from graph <{GRAPH_URI}>...")
    _run_on_stores(stores, "update", _clear_doc_query, args.ref_doc_id, GRAPH_URI)


def cmd_clear_all(args) -> None:
    """Clear the entire named graph (all documents)."""
    stores = _enabled_stores(args)
    if not args.yes:
        confirm = input(f"Clear ALL data from graph <{GRAPH_URI}> in {stores}? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return
    print(f"\nClearing graph <{GRAPH_URI}>...")
    for store in stores:
        clear_fn = STORES[store]["clear"]
        try:
            if clear_fn is not None:
                # Fuseki and Oxigraph: use Graph Store Protocol DELETE (REST)
                clear_fn(GRAPH_URI)
            else:
                # GraphDB: CLEAR GRAPH via SPARQL Update
                STORES[store]["update"](_clear_all_query(GRAPH_URI))
            print(f"  [{store}] OK")
        except Exception as e:
            print(f"  [{store}] ERROR: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Flexible GraphRAG — RDF store cleanup utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List ingested documents across all enabled stores (from .env)
  python scripts/rdf_cleanup.py list-docs

  # Count triples in GraphDB only
  python scripts/rdf_cleanup.py count --graphdb

  # Delete a specific document's triples from Fuseki
  python scripts/rdf_cleanup.py clear-doc 062c8210-ca1e-4a84-b960-baeadfde280d --fuseki

  # Clear everything from all enabled stores (prompts for confirmation)
  python scripts/rdf_cleanup.py clear-all

  # Clear everything without prompt (for scripts)
  python scripts/rdf_cleanup.py clear-all --yes
""")

    # Store selection flags (optional — defaults to whatever is enabled in .env)
    for flag in ("--fuseki", "--graphdb", "--oxigraph"):
        parser.add_argument(flag, action="store_true",
                            help=f"Target {flag[2:]} store")
    parser.add_argument("--neptune-rdf", dest="neptune_rdf", action="store_true",
                        help="Target Amazon Neptune RDF/SPARQL store")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-docs",  help="List ingested documents and triple counts")
    subparsers.add_parser("count",      help="Count total triples in the named graph")

    p_doc = subparsers.add_parser("clear-doc", help="Delete all triples for one document")
    p_doc.add_argument("ref_doc_id", help="The ref_doc_id UUID to delete")

    p_all = subparsers.add_parser("clear-all", help="Clear the entire named graph")
    p_all.add_argument("--yes", "-y", action="store_true",
                       help="Skip confirmation prompt")

    args = parser.parse_args()

    cmds = {
        "list-docs":  cmd_list_docs,
        "count":      cmd_count,
        "clear-doc":  cmd_clear_doc,
        "clear-all":  cmd_clear_all,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    # Load .env — search relative to this script, then relative to cwd
    try:
        from dotenv import load_dotenv
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "flexible-graphrag", ".env"),
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.getcwd(), "..", "flexible-graphrag", ".env"),
        ]
        for env_path in candidates:
            env_path = os.path.normpath(env_path)
            if os.path.exists(env_path):
                load_dotenv(env_path)
                break
    except ImportError:
        pass
    main()
