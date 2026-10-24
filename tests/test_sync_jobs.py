from backend import PROCESSING_STATUS
from incremental_updates import sync_jobs


def test_sync_runs_get_source_label_action_and_keep_history():
    PROCESSING_STATUS.clear()
    cfg = {"alfresco_config": {"nodeDetails": [{"id": "n1", "path": "/Shared/GraphRAG/a.txt"}]}}
    label = sync_jobs.label_for(None, cfg)
    assert label == "/Shared/GraphRAG/a.txt"

    sync_jobs.begin("incremental_alf_n1", "alfresco", label)
    assert PROCESSING_STATUS["incremental_alf_n1"]["sync_action"] == "add"
    PROCESSING_STATUS["incremental_alf_n1"].update(status="completed", documents=["big"])

    with sync_jobs.updating():  # the ADD half of an update, same document id
        sync_jobs.begin("incremental_alf_n1", "alfresco", label)
    entry = PROCESSING_STATUS["incremental_alf_n1"]
    assert entry["sync_action"] == "update" and entry["data_source"] == "alfresco"
    archived = [v for k, v in PROCESSING_STATUS.items() if k.startswith("incremental_alf_n1_")]
    assert len(archived) == 1 and archived[0]["sync_action"] == "add" and "documents" not in archived[0]

    sync_jobs.record_delete("alfresco", "/Shared/GraphRAG/a.txt")
    deleted = [v for v in PROCESSING_STATUS.values() if v.get("sync_action") == "delete"]
    assert deleted[0]["status"] == "completed" and "a.txt" in deleted[0]["message"]
    PROCESSING_STATUS.clear()


def test_label_falls_back_to_object_keys_and_paths():
    assert sync_jobs.label_for(None, {"s3_config": {"key": "docs/b.pdf"}}) == "docs/b.pdf"
    assert sync_jobs.label_for(["C:/data/c.txt"], {}) == "C:/data/c.txt"


def test_processing_ids_are_per_document_and_never_shared():
    # objects under one prefix, and one drive's item ids, share their first characters
    keys = ["kg-autosync-10211435/sel/a.txt", "kg-autosync-10211435/sel/Sub/new1.txt",
            "kg-autosync-10211435/sel/Other/e.txt"]
    ids = [sync_jobs.processing_id("s3", k) for k in keys]
    assert len(set(ids)) == len(keys)
    assert all(i.startswith(sync_jobs.SYNC_PREFIX + "s3_") for i in ids)
    assert sync_jobs.processing_id("msg", "01BNUITGBDXH65ICSTTVBJJF5C4ZNOZLY4") != \
        sync_jobs.processing_id("msg", "01BNUITGGCBB44VO2CXBFKDW5QLSQFJAYB")
    assert sync_jobs.processing_id("s3", keys[0]) == ids[0]   # the same document keeps its id
