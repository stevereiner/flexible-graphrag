"""Unit tests for datasource identity (main._resolve_config_id): two different selections of the
same account / folder / container are two datasources, and a folder-wide one keeps the id it had."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "flexible-graphrag"))

from main import (  # noqa: E402
    AzureBlobConfig, BoxConfig, GoogleDriveConfig, IngestRequest, OneDriveConfig, _resolve_config_id,
    _selection_values,
)

pytestmark = pytest.mark.unit


def _onedrive(**kw):
    cfg = OneDriveConfig(user_principal_name="u@x", client_id="c", client_secret="s", tenant_id="t", **kw)
    return IngestRequest(data_source="onedrive", onedrive_config=cfg)


def test_two_onedrive_folders_of_one_user_are_two_datasources():
    a = _resolve_config_id("onedrive", _onedrive(folder_path="sample-docs"), None)
    b = _resolve_config_id("onedrive", _onedrive(folder_path="kg-matrix"), None)
    assert a != b
    # the whole drive keeps the id it always had; with a folder, the old id is the legacy one
    assert _resolve_config_id("onedrive", _onedrive(), None) == _resolve_config_id(
        "onedrive", _onedrive(folder_path="sample-docs"), None, legacy=True)


def test_file_selections_in_one_folder_or_container_are_two_datasources():
    def drive(ids):
        return IngestRequest(data_source="google_drive", google_drive_config=GoogleDriveConfig(folder_id="f", file_ids=ids))

    assert _resolve_config_id("google_drive", drive(["1"]), None) != _resolve_config_id("google_drive", drive(["2"]), None)
    assert _resolve_config_id("google_drive", drive(["1", "2"]), None) == _resolve_config_id("google_drive", drive(["2", "1"]), None)
    assert _resolve_config_id("google_drive", drive([]), None) == _resolve_config_id("google_drive", drive([]), None, legacy=True)

    def box(ids):
        return IngestRequest(data_source="box", box_config=BoxConfig(folder_id="9", box_file_ids=ids))

    assert _resolve_config_id("box", box(["a"]), None) != _resolve_config_id("box", box(["b"]), None)

    def azure(blob):
        return IngestRequest(data_source="azure_blob", azure_blob_config=AzureBlobConfig(
            container_name="c", account_url="https://a.blob.core.windows.net", blob=blob))

    assert _resolve_config_id("azure_blob", azure("x.txt"), None) != _resolve_config_id("azure_blob", azure("y.txt"), None)


def test_stored_params_compare_like_the_request():
    req = _onedrive(folder_path="kg-matrix")
    stored = req.onedrive_config.model_dump(exclude_none=True)
    assert _selection_values("onedrive", stored) == _selection_values("onedrive", req.onedrive_config)
    assert _selection_values("onedrive", dict(stored, folder_path="sample-docs")) != _selection_values("onedrive", req.onedrive_config)
