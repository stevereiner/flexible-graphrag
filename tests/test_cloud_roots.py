"""Unit tests for the roots of cloud datasources (ingest_status._cloud_roots): a new prefix /
folder sync covers only the syncs inside it, not a bucket- or drive-wide one."""
from types import SimpleNamespace as NS

import pytest

from incremental_updates.ingest_status import Datasource, Item, relate

pytestmark = pytest.mark.unit


def _ds(cid, source_type, **cp):
    return Datasource.from_config(NS(config_id=cid, source_type=source_type, source_name=cid,
                                     connection_params=cp, is_active=True, auto_sync=True))


def _covered(loser, winner):
    return any(m.status == "synced" for r in loser.roots
               for m in relate(Item(r.path, r.is_folder, r.node_id), winner, loser.recursive))


def test_a_prefix_sync_does_not_cover_the_bucket_wide_one():
    win = _ds("w", "s3", bucket_name="b", prefix="kg-matrix3/")
    assert not _covered(_ds("bucket", "s3", bucket_name="b", prefix=""), win)          # was retired
    assert _covered(_ds("sub", "s3", bucket_name="b", prefix="kg-matrix3/Sub/"), win)  # inside it
    assert not _covered(_ds("other", "s3", bucket_name="other", prefix="kg-matrix3/"), win)


def test_cloud_roots_per_source():
    assert _ds("a", "azure_blob", container_name="c", prefix="docs/").roots[0].path == "/c/docs"
    blob = _ds("a", "azure_blob", container_name="c", blob="docs/a.txt").roots[0]
    assert (blob.path, blob.is_folder, blob.node_id) == ("/c/docs/a.txt", False, "docs/a.txt")
    assert _ds("s", "sharepoint", site_name="site-1", folder_path="test").roots[0].path == "/site-1/test"
    assert _ds("o", "onedrive", user_principal_name="u@x", folder_path="kg").roots[0].path == "/u@x/kg"
    assert not _covered(_ds("o1", "onedrive", user_principal_name="u@x", folder_path="sample-docs"),
                        _ds("o2", "onedrive", user_principal_name="u@x", folder_path="kg"))
    assert not _covered(_ds("b1", "box", folder_id="1"), _ds("b2", "box", folder_id="2"))
    assert _ds("g", "google_drive", file_ids=["f1"]).roots[0].node_id == "f1"
    assert _ds("s", "s3", bucket_name="b").recursive
