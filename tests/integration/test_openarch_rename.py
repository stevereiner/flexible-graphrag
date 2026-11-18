"""Can a document be renamed in place through OpenArch's REST API?

OpenArch (checked at 1.0.81) has no rename: an update (PUT / PATCH) ignores ``sys_name``, a move
takes no name, and a move to the document's own parent gives it a generated name. Only copy takes
a name, so ``openarch/writer.py place_source_document`` renames by copy + delete (a new sys_id).
Move and copy also turn a name taken in the target folder into a generated one rather than a 409,
so the writer picks the name (or its unique variant) before it moves.

The in-place rename tests are strict xfails: they xfail while OpenArch lacks a rename and FAIL
(XPASS) once it has one -- the sign that the copy + delete fallback is no longer needed and the
upstream issue (https://github.com/Hyland/OpenArch/issues/11) is fixed.

Talks to OpenArch directly (no backend): ``OPENARCH_URL`` / ``OPENARCH_USERNAME`` /
``OPENARCH_PASSWORD`` in .env. Everything is created in a scratch folder under the root, deleted
at the end. Skips when OpenArch cannot be reached.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

pytestmark = [pytest.mark.integration]

OA_URL = os.getenv("OPENARCH_URL", "http://localhost:8088").rstrip("/")
OA_AUTH = (os.getenv("OPENARCH_USERNAME", "admin"), os.getenv("OPENARCH_PASSWORD", "password"))
DOCS = f"{OA_URL}/api/documents"
ROOT_ID = "00000000-0000-0000-0000-000000000000"

NO_RENAME = "OpenArch has no REST rename (https://github.com/Hyland/OpenArch/issues/11)"


def _call(method, url, body=None, content_type="application/json"):
    r = requests.request(method, url, json=body, auth=OA_AUTH, timeout=30,
                         headers={"Content-Type": content_type, "Accept": "application/json"})
    r.raise_for_status()
    return r.json() if r.content else None


def _create(parent_id, primary_type, name):
    return _call("POST", f"{DOCS}/{parent_id}", {"sys_primaryType": primary_type, "sys_name": name})


def _get(doc_id):
    return _call("GET", f"{DOCS}/{doc_id}")


@pytest.fixture(scope="module")
def folder():
    try:
        requests.get(f"{OA_URL}/actuator/health", timeout=5).raise_for_status()
    except requests.RequestException as e:
        pytest.skip(f"OpenArch not reachable at {OA_URL}: {e}")
    top = _create(ROOT_ID, "SysFolder", f"fg-rename-test-{int(time.time())}")
    yield top
    _call("DELETE", f"{DOCS}/{top['sys_id']}")


@pytest.fixture
def doc(folder, request):
    return _create(folder["sys_id"], "SysFile", f"{request.node.name}.txt")


@pytest.mark.xfail(strict=True, reason=NO_RENAME)
def test_put_sys_name_renames(doc):
    _call("PUT", f"{DOCS}/{doc['sys_id']}", {"sys_name": "put-renamed.txt"})
    assert _get(doc["sys_id"])["sys_name"] == "put-renamed.txt"


@pytest.mark.xfail(strict=True, reason=NO_RENAME)
def test_patch_sys_name_renames(doc):
    _call("PATCH", f"{DOCS}/{doc['sys_id']}", [{"op": "replace", "path": "/sys_name", "value": "patch-renamed.txt"}],
          content_type="application/json-patch+json")
    assert _get(doc["sys_id"])["sys_name"] == "patch-renamed.txt"


@pytest.mark.xfail(strict=True, reason=NO_RENAME)
def test_move_with_name_renames(doc, folder):
    other = _create(folder["sys_id"], "SysFolder", f"other-{doc['sys_id'][:8]}")
    _call("POST", f"{DOCS}/{doc['sys_id']}/move", {"targetParentId": other["sys_id"], "name": "move-renamed.txt"})
    moved = _get(doc["sys_id"])
    assert moved["sys_parentId"] == other["sys_id"]
    assert moved["sys_name"] == "move-renamed.txt"


@pytest.mark.xfail(strict=True, reason="a move to the document's own parent gives it a generated name")
def test_move_to_own_parent_keeps_the_name(doc, folder):
    _call("POST", f"{DOCS}/{doc['sys_id']}/move", {"targetParentId": folder["sys_id"]})
    assert _get(doc["sys_id"])["sys_name"] == doc["sys_name"]


def test_a_taken_name_on_move_or_copy_is_generated_not_a_409(doc, folder):
    """Why writer.py checks for a taken name before a move / copy: those have no enforceSysName,
    so a name taken in the target folder silently becomes ``<name>.<n>`` instead of a 409."""
    other = _create(folder["sys_id"], "SysFolder", f"clash-{doc['sys_id'][:8]}")
    _create(other["sys_id"], "SysFile", doc["sys_name"])
    _call("POST", f"{DOCS}/{doc['sys_id']}/move", {"targetParentId": other["sys_id"]})
    moved = _get(doc["sys_id"])
    assert moved["sys_parentId"] == other["sys_id"]
    assert moved["sys_name"].startswith(doc["sys_name"] + ".")
    copied = _call("POST", f"{DOCS}/{doc['sys_id']}/copy", {"targetParentId": other["sys_id"], "name": doc["sys_name"]})
    assert _get(copied["sys_id"])["sys_name"].startswith(doc["sys_name"] + ".")


def test_copy_with_name_is_a_new_document(doc, folder):
    """The fallback writer.py relies on: copy takes a name, but makes a new document."""
    copied = _call("POST", f"{DOCS}/{doc['sys_id']}/copy", {"targetParentId": folder["sys_id"], "name": "copy-renamed.txt"})
    copied = _get(copied["sys_id"])
    assert copied["sys_name"] == "copy-renamed.txt"
    assert copied["sys_id"] != doc["sys_id"]
