"""Scoped Ask ("Ask about this document / folder") against the configured stores.

Run per store combination with ``run_matrix.py --scope`` (it turns the incremental registry on,
which scoping needs, and points it at a dedicated database). Two Alfresco documents are
ingested with graphs, questions are asked scoped to one of them, and nothing from the other
may come back -- from any store. The documents are then removed with ``/api/sync/remove``,
the app's own removal (so a run cleans up after itself, ``--clean`` or not).

Needs a running Alfresco with a folder (``SCOPE_TEST_FOLDER``, default ``/Shared/GraphRAG``)
holding a file whose name contains ``SCOPE_TEST_IN_SCOPE`` (default ``cmis``) and one whose
name contains ``SCOPE_TEST_OFF_SCOPE`` (default ``space``), and ``ALFRESCO_URL`` /
``ALFRESCO_USERNAME`` / ``ALFRESCO_PASSWORD`` in .env. Skips when Alfresco cannot be reached;
fails when it can but the files are not there.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.scope]

ALF_URL = os.getenv("ALFRESCO_URL", "http://localhost:8080").rstrip("/")
ALF_AUTH = (os.getenv("ALFRESCO_USERNAME", "admin"), os.getenv("ALFRESCO_PASSWORD", "admin"))
FOLDER = os.getenv("SCOPE_TEST_FOLDER", "/Shared/GraphRAG").rstrip("/")
IN_SCOPE = os.getenv("SCOPE_TEST_IN_SCOPE", "cmis").lower()
OFF_SCOPE = os.getenv("SCOPE_TEST_OFF_SCOPE", "space").lower()
IN_TOPIC = os.getenv("SCOPE_TEST_IN_TOPIC", "CMIS content management interoperability")
OFF_TOPIC = os.getenv("SCOPE_TEST_OFF_TOPIC", "space station orbit astronauts")


def _files() -> list:
    """The folder's files: [(name, node id)]. Raises ConnectionError when Alfresco is down."""
    api = f"{ALF_URL}/alfresco/api/-default-/public/alfresco/versions/1/nodes"
    try:
        folder = requests.get(f"{api}/-root-?relativePath={FOLDER.lstrip('/')}", auth=ALF_AUTH, timeout=15)
    except requests.RequestException as e:
        raise ConnectionError(e)
    if folder.status_code == 404:  # Company Home paths: /Shared is the "-shared-" folder
        folder = requests.get(f"{api}/-shared-?relativePath={FOLDER.split('/', 2)[-1]}", auth=ALF_AUTH, timeout=15)
    folder.raise_for_status()
    kids = requests.get(f"{api}/{folder.json()['entry']['id']}/children",
                        params={"where": "(isFile=true)", "maxItems": 100}, auth=ALF_AUTH, timeout=15)
    kids.raise_for_status()
    return [(e["entry"]["name"], e["entry"]["id"]) for e in kids.json()["list"]["entries"]]


def _pick(files: list, fragment: str) -> dict:
    for name, node_id in files:
        if fragment in name.lower():
            return {"id": node_id, "name": name, "path": f"{FOLDER}/{name}", "isFile": True, "isFolder": False}
    pytest.fail(f"no file with {fragment!r} in its name in {FOLDER} (files: {[n for n, _ in files]})")


@pytest.fixture(scope="module")
def ingested(client):
    """Both documents ingested (with graphs, no auto sync); removed again afterwards."""
    try:
        files = _files()
    except ConnectionError as e:
        pytest.skip(f"Alfresco is not reachable at {ALF_URL}: {e}")
    nodes = [_pick(files, IN_SCOPE), _pick(files, OFF_SCOPE)]
    body = {"data_source": "alfresco", "alfresco_config": {
        "url": ALF_URL, "username": ALF_AUTH[0], "password": ALF_AUTH[1],
        "path": FOLDER,
        "nodeIds": [n["id"] for n in nodes], "nodeDetails": nodes}}
    r = client._session.post(f"{client.base_url}/api/ingest", json=body, timeout=120)
    r.raise_for_status()
    status = client.wait_for_completion(r.json()["processing_id"], max_wait=900)
    assert status.status == "completed", status
    # The document_state rows scoping resolves through are written right after the job
    deadline = time.time() + 60
    while time.time() < deadline:
        hits = _search(client, IN_TOPIC, nodes[0])
        if hits.get("results") or "Nothing from" not in str(hits.get("message", "")):
            break
        time.sleep(3)
    yield nodes
    client._session.post(f"{client.base_url}/api/sync/remove", timeout=300, json={
        "data_source": "alfresco", "url": ALF_URL, "recursive": False,
        "items": [{"path": n["path"], "id": n["id"], "is_folder": False} for n in nodes]})


def _scope(node: dict) -> dict:
    return {"data_source": "alfresco", "url": ALF_URL, "node_id": node["id"], "path": node["path"],
            "is_folder": False, "name": node["name"]}


def _search(client, query: str, node: dict) -> dict:
    r = client._session.post(f"{client.base_url}/api/search", timeout=300, json={
        "query": query, "query_type": "hybrid", "top_k": 10, "scope": _scope(node)})
    r.raise_for_status()
    return r.json()


def _leaks(results: list, other: dict) -> list:
    """Results naming the document outside the scope."""
    return [x.get("source") for x in results
            if other["name"] in str(x.get("source", "")) or other["name"] == x.get("file_name")]


def test_scoped_search_returns_nothing_from_other_documents(client, ingested):
    res = _search(client, OFF_TOPIC, ingested[0])
    assert res.get("success", True), res
    assert _leaks(res.get("results") or [], ingested[1]) == []


def test_scoped_search_finds_the_scoped_document(client, ingested):
    res = _search(client, IN_TOPIC, ingested[0])
    results = res.get("results") or []
    assert results, res
    assert _leaks(results, ingested[1]) == []


def test_scoping_to_the_other_document_flips_it(client, ingested):
    """Scoped to the off-scope document instead: now the in-scope one must not appear."""
    res = _search(client, IN_TOPIC, ingested[1])
    assert _leaks(res.get("results") or [], ingested[0]) == []


@pytest.mark.ai_qa
def test_scoped_question_answers(client, ingested):
    r = client._session.post(f"{client.base_url}/api/query", timeout=300, json={
        "query": "What is this document about?", "scope": _scope(ingested[0])})
    r.raise_for_status()
    answer = r.json().get("answer") or ""
    assert answer.strip()
