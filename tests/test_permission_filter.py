"""Unit tests for query-time permission filtering (permission_filter.py), with the repositories mocked."""
import asyncio

import httpx
import pytest

import permission_filter as pf
from permission_filter import Identity

pytestmark = pytest.mark.unit

READABLE = {"n1", "u1", "c1"}  # the mocked repositories let a good credential read only these
ALF = "http://localhost:8080"
NX = "http://localhost:8081/nuxeo"
CMIS = "http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom"
SERVICE_DOC = (
    "<service><cmisra:uritemplate><cmisra:template>" + CMIS + "/id?id={id}&amp;filter={filter}"
    "</cmisra:template><cmisra:type>objectbyid</cmisra:type></cmisra:uritemplate></service>"
)
BAD = {"Basic VElDS0VUX2JhZA==", "bad-token"}  # TICKET_bad (Alfresco) / a revoked Nuxeo token


def _mock_client(*args, **kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        cred = request.headers.get("Authorization") or request.headers.get("X-Authentication-Token")
        assert cred
        if cred in BAD:
            return httpx.Response(401)
        if str(request.url) == CMIS:
            return httpx.Response(200, text=SERVICE_DOC)
        item = request.url.params.get("id") or request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200 if item in READABLE else 403)
    kwargs.pop("timeout", None)
    return _RealClient(transport=httpx.MockTransport(handler))


_RealClient = httpx.AsyncClient


@pytest.fixture(autouse=True)
def mocked_repositories(monkeypatch):
    pf._cache.clear()
    pf._cmis_templates.clear()
    monkeypatch.setattr(httpx, "AsyncClient", _mock_client)


def alf(ticket="TICKET_ok", url=ALF):
    import base64
    return Identity("alfresco", url, {"Authorization": "Basic " + base64.b64encode(ticket.encode()).decode()})


def nx(token="good-token", url=NX):
    return Identity("nuxeo", url, {"X-Authentication-Token": token})


def run(ids, identities, server=lambda d: None, required=lambda s: True):
    return asyncio.run(pf.readable_doc_ids(ids, identities, server,
                                           {"alfresco": ALF, "nuxeo": NX, "cmis": CMIS}, required))


def test_refs_and_server_keys():
    assert pf.governed_ref("c1:alfresco://n1") == ("alfresco", "n1")
    assert pf.governed_ref("c1:nuxeo://u1") == ("nuxeo", "u1")
    assert pf.governed_ref("c1:cmis://abc;1.0") == ("cmis", "abc;1.0")
    assert pf.governed_ref("c1:/data/file.txt") is None
    assert pf.config_id_of("c1:nuxeo://u1") == "c1"
    assert pf.alfresco_node_id("c1:alfresco://n1") == "n1"
    assert pf._rest_base("http://localhost:8080/alfresco/") == "http://localhost:8080"
    assert pf.server_key("alfresco", "http://LOCALHOST:8080/alfresco") == pf.server_key("alfresco", ALF)


def test_keeps_readable_docs_of_each_source_and_ungoverned_docs():
    ids = ["c1:alfresco://n1", "c1:alfresco://n2", "c2:nuxeo://u1", "c2:nuxeo://u2", "c3:/data/notes.txt"]
    out = run(ids, [alf(), nx()])
    assert out.doc_ids == ["c1:alfresco://n1", "c2:nuxeo://u1", "c3:/data/notes.txt"]
    assert out.unsigned == set()


def test_cmis_uses_the_objectbyid_template():
    out = run(["c4:cmis://c1", "c4:cmis://c2"], [Identity("cmis", CMIS, {"Authorization": "Basic x"})])
    assert out.doc_ids == ["c4:cmis://c1"]


def test_no_identity_for_a_required_source_leaves_it_out():
    out = run(["c1:alfresco://n1", "c2:nuxeo://u1"], [alf()])
    assert out.doc_ids == ["c1:alfresco://n1"]
    assert out.unsigned == {"nuxeo"}


def test_optional_source_without_identity_stays_visible():
    out = run(["c2:nuxeo://u2"], [], required=lambda s: s != "nuxeo")
    assert out.doc_ids == ["c2:nuxeo://u2"]


def test_identity_is_matched_to_the_documents_server():
    other = "http://other:8080"
    out = run(["c1:alfresco://n1", "c9:alfresco://n1"], [alf(), alf("TICKET_two", other)],
              server=lambda d: other if d.startswith("c9") else ALF)
    assert out.doc_ids == ["c1:alfresco://n1", "c9:alfresco://n1"]
    # only the first server's identity: the second server's document is left out, not checked
    out = run(["c1:alfresco://n1", "c9:alfresco://n1"], [alf()],
              server=lambda d: other if d.startswith("c9") else ALF)
    assert out.doc_ids == ["c1:alfresco://n1"]


def test_refused_credential_raises_with_its_source():
    with pytest.raises(pf.CredentialRefused) as e:
        run(["c2:nuxeo://u1"], [nx("bad-token")])
    assert e.value.source == "nuxeo"
    with pytest.raises(PermissionError):
        run(["c1:alfresco://n1"], [alf("TICKET_bad")])
