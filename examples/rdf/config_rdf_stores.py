import os, json
from rdf_store_factory import RDFStoreFactory

enabled = os.getenv("RDF_ENABLED_STORES", "")
enabled_names = [n.strip() for n in enabled.split(",") if n.strip()]

stores_cfg = json.loads(os.getenv("RDF_STORES_JSON", "{}"))

rdf_stores = {}
for name in enabled_names:
    spec = stores_cfg.get(name)
    if not spec:
        continue
    rdf_stores[name] = RDFStoreFactory.create(spec["type"], spec["config"])

if "fuseki" in os.getenv("RDF_ENABLED_STORES", ""):
    rdf_stores["fuseki"] = RDFStoreFactory.create("fuseki", {
        "base_url": os.getenv("FUSEKI_BASE_URL", "http://localhost:3030"),
        "dataset": os.getenv("FUSEKI_DATASET", "flexible-graphrag"),
    })

if "graphdb" in os.getenv("RDF_ENABLED_STORES", ""):
    rdf_stores["graphdb"] = RDFStoreFactory.create("graphdb", {
        "base_url": os.getenv("GRAPHDB_BASE_URL", "http://localhost:7200"),
        "repository": os.getenv("GRAPHDB_REPOSITORY", "flexible-graphrag"),
        "username": os.getenv("GRAPHDB_USERNAME", "admin"),
        "password": os.getenv("GRAPHDB_PASSWORD", "admin"),
    })

if "oxigraph" in os.getenv("RDF_ENABLED_STORES", ""):
    rdf_stores["oxigraph"] = RDFStoreFactory.create("oxigraph", {
        "store_path": os.getenv("OXIGRAPH_STORE_PATH", "./data/oxigraph_store"),
    })    
