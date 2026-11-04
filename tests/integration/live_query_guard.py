"""Live check of the graph Q&A write guard against the Docker graph databases.

usage (from the repo root, with the project venv):
    python tests/integration/live_query_guard.py [store ...]

stores: neo4j memgraph falkordb age arcadedb ladybug gremlin arangodb surrealdb hugegraph
        tigergraph nebula graphdb fuseki oxigraph   (default: all)

Not a pytest module: it needs the Docker stack, and it writes to the databases. Connection
settings come from flexible-graphrag/.env (*_GRAPH_DB_CONFIG, GRAPHDB_*, FUSEKI_*, OXIGRAPH_URL);
the Gremlin check uses the local TinkerPop server (ws://localhost:8182), not Cosmos DB.

For each store it builds the app's real QA chain (LCGraphQARetriever.from_graph) on the adapter's
LangChain graph, with a stand-in LLM that always answers with one fixed query. Then:
  1. ingest a marker node AFTER the guard is installed   -> ingest must still write
  2. an LLM that writes a READ of the marker              -> must not be refused
  3. an LLM that writes a DELETE of the marker            -> must be refused, marker must survive
  4. control: the same DELETE through the chain outside graph Q&A. "deleted" shows the chain really
     runs it. "kept" is expected where generated queries go through the store's own code, which
     checks every query (ArangoDB, HugeGraph, TigerGraph, GraphDB), and on Fuseki / Oxigraph, whose
     SPARQL query endpoint does not run updates.

Destructive queries only target the marker (label FGSecGuard / id fgsec-guard / named graph
<http://fgsec/guard>), so a failure can only delete the marker. Stores that allow it get a
throwaway graph or database (fg_sec_guard); Neo4j, Memgraph, HugeGraph, TigerGraph and the RDF
stores are shared, and only the marker is written there and removed at the end.
"""
import json
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "flexible-graphrag"
STORES = sys.argv[1:] or ["neo4j", "memgraph", "falkordb", "age", "arcadedb", "ladybug", "gremlin",
                          "arangodb", "surrealdb", "hugegraph", "tigergraph", "nebula",
                          "graphdb", "fuseki", "oxigraph"]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
logging.basicConfig(level=logging.WARNING)  # warnings reach Capture below ...
logging.getLogger().handlers[0].setLevel(logging.CRITICAL)  # ... but stay off the console

from dotenv import dotenv_values  # noqa: E402
from langchain_community.graphs.graph_document import GraphDocument, Node  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402

from langchain.graph.retrievers import query_guard  # noqa: E402
from langchain.graph.retrievers.lc_graph_retriever import LCGraphQARetriever, _build_qa_chain  # noqa: E402

ENV = dotenv_values(ROOT / ".env")
MARK, MID, TEST_DB = "FGSecGuard", "fgsec-guard", "fg_sec_guard"
RDF_GRAPH, RDF_NODE = "<http://fgsec/guard>", "<http://fgsec/n>"

REFUSALS = []
_orig_init = query_guard.WriteQueryRefused.__init__


def _record(self, *a, **kw):  # chains often catch the refusal themselves: count it at the source
    REFUSALS.append(str(a[0]) if a else "")
    _orig_init(self, *a, **kw)


query_guard.WriteQueryRefused.__init__ = _record
# The schema was read before the marker existed: don't let the empty-schema shortcut skip the chain
LCGraphQARetriever._graph_is_empty = lambda self: False


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


CAP = Capture()
logging.getLogger().addHandler(CAP)
RESULTS = {}


def env_cfg(key):
    return json.loads(ENV[key])


def marker_doc():
    return [GraphDocument(nodes=[Node(id=MID, type=MARK)], relationships=[],
                          source=Document(page_content="fgsec guard", metadata={"ref_doc_id": "fgsec-guard-doc"}))]


def ask(graph, query):
    """Run one question through the real chain with an LLM that answers `query`."""
    CAP.msgs.clear()
    REFUSALS.clear()
    r = LCGraphQARetriever.from_graph(graph, FakeListChatModel(responses=[query]), include_intermediate_steps=True)
    docs = r.invoke("fgsec question")
    # ArangoDB raises the library's own error, with our reason, from its read-only hook
    return docs, REFUSALS[:] + [m for m in CAP.msgs if "Security violation" in m]


def check(store, graph, seed, count, read_q, write_q, cleanup=lambda: None):
    try:
        LCGraphQARetriever.from_graph(graph, FakeListChatModel(responses=["x"]))  # installs the guard
        seed()
        before = count()
        docs, read_refused = ask(graph, read_q)
        _, write_refused = ask(graph, write_q)
        after = count()
        try:
            _build_qa_chain(graph, FakeListChatModel(responses=[write_q])).invoke({"query": "fgsec question"})
        except Exception:
            pass
        control = count()
        ok = before >= 1 and after == before and bool(write_refused) and not read_refused
        RESULTS[store] = ok
        print(f"[{store:10}] ingest after guard: {before}  read refused: {bool(read_refused)} "
              f"(docs {len(docs)})  delete refused: {bool(write_refused)}  marker after: {after}  "
              f"-> {'PASS' if ok else 'FAIL'}   | control: {'deleted' if control < after else 'kept'}")
        if not ok:
            print(f"             read: {read_refused[:1]}  write: {write_refused[:1]}  log: {CAP.msgs[-3:]}")
    finally:
        try:
            cleanup()
        except Exception as e:
            print(f"[{store:10}] cleanup: {type(e).__name__}: {str(e)[:150]}")


CY_READ = f"MATCH (n:{MARK}) RETURN n.id AS id"
CY_DEL = f"MATCH (n:{MARK}) DETACH DELETE n"


def bolt_count(g, q=f"MATCH (n:{MARK}) RETURN count(n) AS c"):
    r = g.query(q)[0]
    return r["c"] if isinstance(r, dict) else r[0]


# ── Cypher stores ───────────────────────────────────────────────────────────

def t_neo4j():  # shared database
    from langchain.graph.pg_store_adapters.neo4j_adapter import Neo4jAdapter
    g = Neo4jAdapter(env_cfg("NEO4J_GRAPH_DB_CONFIG")).lc_graph
    check("neo4j", g, lambda: g.add_graph_documents(marker_doc()), lambda: bolt_count(g), CY_READ, CY_DEL,
          lambda: g.query(f"MATCH (n:{MARK}) DETACH DELETE n"))


def t_memgraph():  # one database: shared
    from langchain.graph.pg_store_adapters.memgraph_adapter import MemgraphAdapter
    a = MemgraphAdapter(env_cfg("MEMGRAPH_GRAPH_DB_CONFIG"))
    g = a.lc_graph
    check("memgraph", g, lambda: a.add_graph_documents(marker_doc()), lambda: bolt_count(g), CY_READ, CY_DEL,
          lambda: g.query(f"MATCH (n:{MARK}) DETACH DELETE n"))


def t_falkordb():
    from langchain.graph.pg_store_adapters.falkordb_adapter import FalkorDBAdapter
    a = FalkorDBAdapter({**env_cfg("FALKORDB_GRAPH_DB_CONFIG"), "database": TEST_DB})
    g = a.lc_graph
    check("falkordb", g, lambda: a.add_graph_documents(marker_doc()), lambda: bolt_count(g), CY_READ, CY_DEL,
          lambda: g._graph.delete())


def t_age():
    import psycopg2
    from langchain.graph.pg_store_adapters.apache_age_adapter import ApacheAGEAdapter
    cfg = {**env_cfg("APACHE_AGE_GRAPH_DB_CONFIG"), "graph_name": TEST_DB}

    def sql(s):
        conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], dbname=cfg["database"],
                                user=cfg["username"], password=cfg["password"])
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("LOAD 'age'")
            cur.execute('SET search_path = ag_catalog, "$user", public')
            cur.execute(s)
            rows = cur.fetchall() if cur.description else []
        conn.close()
        return rows

    if sql(f"SELECT count(*) FROM ag_catalog.ag_graph WHERE name = '{TEST_DB}'")[0][0]:
        sql(f"SELECT drop_graph('{TEST_DB}', true)")
    a = ApacheAGEAdapter(cfg)

    def count():
        try:
            return int(str(sql(f"SELECT * FROM cypher('{TEST_DB}', $q$MATCH (n:{MARK}) RETURN count(n)$q$) "
                               "AS (c agtype)")[0][0]))
        except Exception:
            return 0
    check("age", a.lc_graph, lambda: a.add_graph_documents(marker_doc()), count, CY_READ, CY_DEL,
          lambda: sql(f"SELECT drop_graph('{TEST_DB}', true)"))


def t_arcadedb():
    import requests
    from langchain.graph.pg_store_adapters.arcadedb_lc_adapter import ArcadeDBLangChainAdapter
    cfg = {**env_cfg("ARCADEDB_GRAPH_DB_CONFIG"), "database": TEST_DB}
    a = ArcadeDBLangChainAdapter(cfg)
    g = a.lc_graph
    check("arcadedb", g, lambda: a.add_graph_documents(marker_doc()), lambda: bolt_count(g), CY_READ, CY_DEL,
          lambda: requests.post(f"http://{cfg['host']}:{cfg['port']}/api/v1/server",
                                auth=(cfg["username"], cfg["password"]),
                                json={"command": f"drop database {TEST_DB}"}, timeout=30))


def t_ladybug():  # embedded: a temp directory
    from langchain.graph.pg_store_adapters.ladybug_adapter import LangChainLadybugAdapter
    a = LangChainLadybugAdapter({"db_dir": tempfile.mkdtemp(prefix="fgsec-guard-ladybug-")})

    def count():
        try:
            return a.lc_graph.conn.execute(f"MATCH (n:{MARK}) RETURN count(n)").get_next()[0]
        except Exception:
            return 0
    check("ladybug", a.lc_graph, lambda: a.add_graph_documents(marker_doc()), count, CY_READ, CY_DEL)


def t_hugegraph():  # shared graph; every entity has label __Entity__, keyed by node id
    from langchain.graph.pg_store_adapters.hugegraph_adapter import HugeGraphAdapter
    a = HugeGraphAdapter(env_cfg("HUGEGRAPH_GRAPH_DB_CONFIG"))
    g = a.lc_graph
    check("hugegraph", g, lambda: a.add_graph_documents(marker_doc()),
          lambda: g.query(f"g.V('{MID}').count()")[0],
          f"MATCH (n) WHERE id(n) = '{MID}' RETURN n",
          f"MATCH (n) WHERE id(n) = '{MID}' DETACH DELETE n",
          lambda: g.query(f"g.V('{MID}').drop()"))


# ── Other query languages ───────────────────────────────────────────────────

def t_gremlin():  # local TinkerPop Gremlin Server, through the Cosmos adapter
    from langchain.graph.pg_store_adapters.cosmos_gremlin_adapter import CosmosDBGremlinAdapter
    a = CosmosDBGremlinAdapter({"url": "ws://localhost:8182/gremlin", "username": "/", "password": ""})
    g = a.lc_graph
    check("gremlin", g, lambda: a.add_graph_documents(marker_doc()),
          lambda: g.query(f"g.V().hasLabel('{MARK}').count()")[0],
          f"g.V().hasLabel('{MARK}').values('id')", f"g.V().hasLabel('{MARK}').drop()",
          lambda: g.query(f"g.V().hasLabel('{MARK}').drop()"))


def t_arangodb():
    from arango import ArangoClient
    from langchain.graph.pg_store_adapters.arangodb_adapter import ArangoDBAdapter
    cfg = env_cfg("ARANGODB_GRAPH_DB_CONFIG")
    sysdb = ArangoClient(hosts=cfg["url"]).db("_system", username=cfg["username"], password=cfg["password"])
    if sysdb.has_database(TEST_DB):
        sysdb.delete_database(TEST_DB)
    sysdb.create_database(TEST_DB)
    a = ArangoDBAdapter({**cfg, "database": TEST_DB, "graph_name": "fgsec"})
    db = ArangoClient(hosts=cfg["url"]).db(TEST_DB, username=cfg["username"], password=cfg["password"])

    def count():
        if not db.has_collection("fgsec_ENTITY"):
            return 0
        return len(list(db.aql.execute("FOR e IN fgsec_ENTITY RETURN 1")))
    check("arangodb", a.lc_graph, lambda: a.add_graph_documents(marker_doc()), count,
          "```aql\nFOR e IN fgsec_ENTITY RETURN e.text\n```",
          "```aql\nFOR e IN fgsec_ENTITY REMOVE e IN fgsec_ENTITY\n```",
          lambda: sysdb.delete_database(TEST_DB))


def t_surrealdb():  # node types become graph_<Type> tables
    from langchain.graph.pg_store_adapters.surrealdb_adapter import SurrealDBAdapter
    a = SurrealDBAdapter({**env_cfg("SURREALDB_GRAPH_DB_CONFIG"), "database": TEST_DB})
    conn = a.lc_graph.connection

    def count():
        try:
            r = conn.query(f"SELECT count() AS c FROM graph_{MARK} GROUP ALL")
        except Exception:
            return 0
        return r[0]["c"] if r else 0
    check("surrealdb", a.lc_graph, lambda: a.add_graph_documents(marker_doc()), count,
          f"SELECT * FROM graph_{MARK}", f"DELETE graph_{MARK}", lambda: conn.query(f"REMOVE DATABASE {TEST_DB}"))


def t_tigergraph():  # shared graph: one __Entity__ vertex with id fgsec-guard
    from langchain.graph.pg_store_adapters.tigergraph_adapter import TigerGraphAdapter
    a = TigerGraphAdapter(env_cfg("TIGERGRAPH_GRAPH_DB_CONFIG"))
    g = a.lc_graph
    conn = g.conn if hasattr(g, "conn") else a.conn
    body = 'Seed = {__Entity__.*};\n  R = SELECT s FROM Seed:s WHERE s.id == "%s"' % MID
    check("tigergraph", g, lambda: a.add_graph_documents(marker_doc()),
          lambda: len(conn.getVerticesById("__Entity__", MID) or []),
          "INTERPRET QUERY() FOR GRAPH MyGraph {\n  %s;\n  PRINT R;\n}" % body,
          "INTERPRET QUERY() FOR GRAPH MyGraph {\n  %s;\n  DELETE s FROM R:s;\n  PRINT R;\n}" % body,
          lambda: conn.delVerticesById("__Entity__", MID))


def t_nebula():
    from nebula3.Config import Config
    from nebula3.gclient.net import ConnectionPool
    from langchain.graph.pg_store_adapters.nebula_adapter import NebulaGraphAdapter
    cfg = env_cfg("NEBULA_GRAPH_DB_CONFIG")
    host, port = cfg.get("host") or cfg.get("address", "localhost"), int(cfg.get("port", 9669))
    a = NebulaGraphAdapter({**cfg, "host": host, "space": TEST_DB})
    g = a.lc_graph

    def count():
        r = g.query(f'FETCH PROP ON * "{MID}" YIELD id(vertex) AS i')
        return len(r.get("i", [])) if isinstance(r, dict) else len(r or [])

    def seed():
        time.sleep(25)  # a new space needs heartbeats before writes land
        a.add_graph_documents(marker_doc())
        time.sleep(5)

    def drop_space():
        pool = ConnectionPool()
        pool.init([(host, port)], Config())
        s = pool.get_session(cfg.get("username", "root"), cfg.get("password", "nebula"))
        s.execute(f"DROP SPACE IF EXISTS {TEST_DB}")
        s.release()
        pool.close()
    check("nebula", g, seed, count, f'FETCH PROP ON * "{MID}" YIELD vertex AS v',
          f'DELETE VERTEX "{MID}" WITH EDGE', drop_space)


# ── RDF stores: one named graph <http://fgsec/guard> in the shared dataset ──

def sparql_check(store, graph, query_url, update_url, auth):
    import requests

    def upd(q):
        requests.post(update_url, data={"update": q}, auth=auth, timeout=30).raise_for_status()

    def count():
        r = requests.post(query_url, data={"query": f"SELECT (COUNT(*) AS ?c) WHERE {{ GRAPH {RDF_GRAPH} {{ ?s ?p ?o }} }}"},
                          headers={"Accept": "application/sparql-results+json"}, auth=auth, timeout=30)
        r.raise_for_status()
        return int(r.json()["results"]["bindings"][0]["c"]["value"])
    check(store, graph,
          lambda: upd(f'INSERT DATA {{ GRAPH {RDF_GRAPH} {{ {RDF_NODE} '
                      f'<http://www.w3.org/2000/01/rdf-schema#label> "fgsec guard" }} }}'),
          count,
          f"SELECT ?p ?o WHERE {{ GRAPH {RDF_GRAPH} {{ {RDF_NODE} ?p ?o }} }}",
          f"DELETE WHERE {{ GRAPH {RDF_GRAPH} {{ ?s ?p ?o }} }}",
          lambda: upd(f"DROP SILENT GRAPH {RDF_GRAPH}"))


def t_graphdb():
    from langchain.graph.rdf_store_adapters.graphdb_langchain_adapter import GraphDBLangChainAdapter
    base, repo = ENV.get("GRAPHDB_BASE_URL", "http://localhost:7200"), ENV.get("GRAPHDB_REPOSITORY", "flexible-graphrag")
    auth = (ENV.get("GRAPHDB_USERNAME"), ENV.get("GRAPHDB_PASSWORD"))
    os.environ["GRAPHDB_USERNAME"], os.environ["GRAPHDB_PASSWORD"] = auth  # read by the GraphDB chain
    a = GraphDBLangChainAdapter({"base_url": base, "repository": repo, "username": auth[0],
                                 "password": auth[1], "sparql_results_format": "json"})
    url = f"{base}/repositories/{repo}"
    sparql_check("graphdb", a.lc_graph, url, url + "/statements", auth)


def t_fuseki():
    from langchain.graph.rdf_store_adapters.fuseki_langchain_adapter import FusekiLangChainAdapter
    base, ds = ENV.get("FUSEKI_BASE_URL", "http://localhost:3030"), ENV.get("FUSEKI_DATASET", "flexible-graphrag")
    user, pwd = ENV.get("FUSEKI_USERNAME"), ENV.get("FUSEKI_PASSWORD")
    cfg = {"base_url": base, "dataset": ds, **({"username": user} if user else {}), **({"password": pwd} if pwd else {})}
    a = FusekiLangChainAdapter(cfg)
    sparql_check("fuseki", a.lc_graph, f"{base}/{ds}/query", f"{base}/{ds}/update", (user, pwd) if user else None)


def t_oxigraph():
    from langchain.graph.rdf_store_adapters.oxigraph_langchain_adapter import OxigraphLangChainAdapter
    url = ENV.get("OXIGRAPH_URL", "http://localhost:7878")
    a = OxigraphLangChainAdapter({"url": url})
    sparql_check("oxigraph", a.lc_graph, f"{url}/query", f"{url}/update", None)


for name in STORES:
    try:
        globals()[f"t_{name}"]()
    except Exception as e:
        RESULTS[name] = False
        print(f"[{name:10}] ERROR {type(e).__name__}: {str(e)[:300]}")
        traceback.print_exc(limit=3)

failed = [s for s, ok in RESULTS.items() if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} stores passed" + (f"; failed: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
