"""The auto-sync scenarios. Each takes a Ctx and records checks on ctx.report; they run in the
order of ORDER, later ones relying on what earlier ones left (see sources.LAYOUT).

Most ingests build no graphs (enabled_graph / enabled_rdf false); only the graphs scenario turns
both on, for a small set of sources (run_autosync.py --graph-sources).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from harness import Backend, Report, Tree, TreeDoc, under, wait
from sources import Source

GRACE = 30   # seconds a change that must NOT be followed gets before it is checked


@dataclass
class Ctx:
    src: Source
    backend: Backend
    tree: Tree
    report: Report
    tag: str
    configs: Dict[str, str] = field(default_factory=dict)   # scenario -> config_id
    late_wait: int = 100

    # the tree ---------------------------------------------------------------------------
    def docs(self, folder: str) -> Dict[str, TreeDoc]:
        return self.tree.docs(self.src.tree_type, self.src.tree_key(folder), self.src.case_insensitive)

    def _k(self, rel: str) -> str:
        return rel.lower() if self.src.case_insensitive else rel

    def entry(self, folder: str, rel: str, config: Optional[str]) -> Optional[Dict[str, Any]]:
        d = self.docs(folder).get(self._k(rel))
        return d.state(config) if d else None

    def followed(self, folder: str, rel: str, config: Optional[str]) -> bool:
        return self.entry(folder, rel, config) is not None

    def snapshot(self, folder: str, rel: str, config: Optional[str]) -> Optional[str]:
        e = self.entry(folder, rel, config)
        return e.get("contentHash") if e else None

    def edited(self, folder: str, rel: str, config: Optional[str], before: Optional[str], marker: str) -> bool:
        d = self.docs(folder).get(self._k(rel))
        e = d.state(config) if d else None
        if not e:
            return False
        if d.text:   # ENABLE_OPENARCH: the tree holds the text
            return marker in d.text
        return e.get("contentHash") != before

    # checks -----------------------------------------------------------------------------
    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        return self.report.check(name, ok, detail)

    def wait_check(self, name: str, pred: Callable[[], bool], timeout: Optional[int] = None) -> bool:
        secs = wait(pred, timeout or self.src.timeout)
        return self.check(name, secs is not None, f"{secs} s" if secs is not None else f"not within {timeout or self.src.timeout} s")

    def ingest(self, what: str, body: Dict[str, Any]) -> Dict[str, Any]:
        job = self.backend.ingest(body)
        self.check(f"{what}: ingest completed", job.get("status") == "completed",
                   f"{job.get('status')}: {(job.get('message') or '')[:160]}")
        return job

    def mark(self, letter: str) -> str:
        return f"{self.tag}{letter}{int(time.time()) % 100000}"


# ── scenarios ────────────────────────────────────────────────────────────────────────────────

def select(c: Ctx) -> None:
    """Multiselect (a file and a folder, not recursive) or the whole sel/ folder, with auto sync."""
    s = c.src
    if s.multiselect:
        job = c.ingest("multiselect a.txt + Sub", s.body("sel", recursive=False, select=["sel/a.txt", "sel/Sub"]))
        cfg = c.configs["sel"] = job.get("config_id")
        time.sleep(5)
        c.check("a.txt (selected file) followed", c.followed("sel", "a.txt", cfg))
        c.check("Sub/c.txt (in the selected folder) followed", c.followed("sel", "Sub/c.txt", cfg))
        if s.recursive_option:
            c.check("Sub/Deep/d.txt not followed (not recursive)", not c.followed("sel", "Sub/Deep/d.txt", cfg))
        else:
            c.check("Sub/Deep/d.txt followed (folders are recursive)", c.followed("sel", "Sub/Deep/d.txt", cfg))
        for rel in ("b.txt", "m.txt", "Other/e.txt"):
            c.check(f"{rel} not followed (not selected)", not c.followed("sel", rel, cfg))
    else:
        job = c.ingest("folder sel/", s.body("sel"))
        cfg = c.configs["sel"] = job.get("config_id")
        time.sleep(5)
        for rel in ("a.txt", "b.txt", "m.txt", "Sub/c.txt", "Sub/Deep/d.txt", "Other/e.txt"):
            c.check(f"{rel} followed", c.followed("sel", rel, cfg))
    c.check("nothing from out/ followed", not any(d.state(cfg) for d in c.docs("out").values()))


def search(c: Ctx) -> None:
    """The ingested text is found by hybrid search (with the source's sign-in for repositories)."""
    results = c.backend.search(f"{c.tag} beacon Corrin northern pass", top_k=10, source_auth=c.src.source_auth())
    text = json.dumps(results)
    c.check("hybrid search finds a.txt's text", c.tag in text and "Corrin" in text, f"{len(results)} results")


def follow(c: Ctx) -> None:
    """A new file in scope, an edit, and new files out of scope."""
    s, cfg = c.src, c.configs.get("sel")
    m = c.mark("F")
    before = c.snapshot("sel", "a.txt", cfg)
    s.put("sel/Sub/new1.txt", f"{m} new in Sub.")
    s.put("sel/a.txt", f"{m} file a edited: the beacon Corrin guards the northern pass.")
    s.put("out/new-out.txt", f"{m} new outside every sync.")
    outside = []
    if s.multiselect:
        s.put("sel/new-root.txt", f"{m} new at sel/'s root (not selected).")
        outside.append(("new-root.txt", "not selected"))
        if s.recursive_option:
            s.put("sel/Sub/Deep/new2.txt", f"{m} new in Sub/Deep (not recursive).")
            outside.append(("Sub/Deep/new2.txt", "not recursive"))
    c.wait_check("new file in Sub followed", lambda: c.followed("sel", "Sub/new1.txt", cfg))
    c.wait_check("edit of a.txt followed", lambda: c.edited("sel", "a.txt", cfg, before, m))
    time.sleep(GRACE)
    for rel, why in outside:
        c.check(f"{rel} not followed ({why})", not c.followed("sel", rel, cfg))
    c.check("out/new-out.txt not followed", not c.followed("out", "new-out.txt", cfg))


def delete(c: Ctx) -> None:
    cfg = c.configs.get("sel")
    c.src.delete("sel/Sub/new1.txt")
    c.wait_check("deleted Sub/new1.txt gone from the tree", lambda: not c.followed("sel", "Sub/new1.txt", cfg))


def move(c: Ctx) -> None:
    s, cfg = c.src, c.configs.get("sel")
    s.rename("sel/Sub/c.txt", "c2.txt")
    c.wait_check("rename Sub/c.txt -> Sub/c2.txt followed",
                 lambda: c.followed("sel", "Sub/c2.txt", cfg) and not c.followed("sel", "Sub/c.txt", cfg))
    if s.multiselect:
        s.move("sel/Sub/c2.txt", "sel/Other")
        c.wait_check("Sub/c2.txt moved to Other (out of the selection) gone",
                     lambda: not c.followed("sel", "Sub/c2.txt", cfg))
        c.check("Other/c2.txt not followed", not c.followed("sel", "Other/c2.txt", cfg))
        if s.recursive_option:   # repositories follow a selected file by id
            s.rename("sel/a.txt", "a-renamed.txt")
            c.wait_check("selected a.txt renamed: a-renamed.txt followed, a.txt gone",
                         lambda: c.followed("sel", "a-renamed.txt", cfg) and not c.followed("sel", "a.txt", cfg))
    else:
        s.move("sel/m.txt", "out")
        c.wait_check("m.txt moved to out/ gone", lambda: not c.followed("sel", "m.txt", cfg))
        c.check("out/m.txt not followed", not c.followed("out", "m.txt", cfg))
        s.move("sel/a.txt", "sel/Sub")
        c.wait_check("a.txt moved into Sub followed there",
                     lambda: c.followed("sel", "Sub/a.txt", cfg) and not c.followed("sel", "a.txt", cfg))


def folder(c: Ctx) -> None:
    """A folder rename inside the sync's scope (repositories: see recursive)."""
    s, cfg = c.src, c.configs.get("sel")
    # Sources whose events don't cover a folder's files (Microsoft Graph's delta) leave it to the
    # periodic refresh: refresh every 60 s instead of the default, so it comes within the wait
    if cfg:
        try:
            c.backend.set_interval(cfg, 60)
        except Exception as e:
            c.report.note(f"interval not set: {e}")
    s.rename_folder("sel/Sub/Deep", "Deeper")
    c.wait_check("folder Sub/Deep renamed: Sub/Deeper/d.txt followed, Sub/Deep/d.txt gone",
                 lambda: c.followed("sel", "Sub/Deeper/d.txt", cfg) and not c.followed("sel", "Sub/Deep/d.txt", cfg),
                 timeout=max(c.src.timeout, 540))


def rule(c: Ctx) -> None:
    """A Processing row (Sub) with Auto Sync off: its new files and edits are not followed."""
    s, cfg = c.src, c.configs.get("sel")
    s.put("sel/Sub/r.txt", f"{c.mark('R')} in Sub before its auto sync goes off.")
    c.wait_check("Sub/r.txt followed (before the rule)", lambda: c.followed("sel", "Sub/r.txt", cfg))
    body = {"data_source": s.name, "enabled_graph": False, "enabled_rdf": False,
            "item_actions": [s.row("sel/Sub", "keep", auto_sync=False)]}
    body.update(s.config("sel", recursive=False))
    c.ingest("row Sub: Auto Sync off", body)
    st = c.backend.ingest_status(s.status_body(["sel/Sub/r.txt"], "sel", recursive=False))
    item = (st.get("items") or [{}])[0]
    c.check("ingest status: Sub/r.txt auto sync off", item.get("auto_sync") is False, f"auto_sync={item.get('auto_sync')}")
    before = c.snapshot("sel", "Sub/r.txt", cfg)
    m = c.mark("R")
    s.put("sel/Sub/new3.txt", f"{m} new in Sub after its auto sync went off.")
    s.put("sel/Sub/r.txt", f"{m} edit in Sub after its auto sync went off.")
    time.sleep(GRACE + 15)
    c.check("Sub/new3.txt not followed (Sub's auto sync off)", not c.followed("sel", "Sub/new3.txt", cfg))
    c.check("edit of Sub/r.txt not followed", not c.edited("sel", "Sub/r.txt", cfg, before, m))
    c.check("Sub/r.txt kept in the tree", c.followed("sel", "Sub/r.txt", cfg))


def recursive(c: Ctx) -> None:
    """A recursive root: nested files, a new nested file, a move up, a folder rename."""
    s = c.src
    job = c.ingest("folder rec/ recursive", s.body("rec", recursive=True))
    cfg = c.configs["rec"] = job.get("config_id")
    time.sleep(5)
    c.check("rec/r1.txt followed", c.followed("rec", "r1.txt", cfg))
    c.check("rec/Deep/r2.txt followed (recursive)", c.followed("rec", "Deep/r2.txt", cfg))
    s.put("rec/Deep/new4.txt", f"{c.mark('C')} new in Deep of a recursive root.")
    c.wait_check("new file in rec/Deep followed", lambda: c.followed("rec", "Deep/new4.txt", cfg))
    s.move("rec/Deep/r2.txt", "rec")
    c.wait_check("Deep/r2.txt moved up: r2.txt followed at the root, Deep/r2.txt gone",
                 lambda: c.followed("rec", "r2.txt", cfg) and not c.followed("rec", "Deep/r2.txt", cfg))
    s.rename_folder("rec/Deep", "Deeper")
    c.wait_check("folder Deep renamed: Deeper/new4.txt followed, Deep/new4.txt gone",
                 lambda: c.followed("rec", "Deeper/new4.txt", cfg) and not c.followed("rec", "Deep/new4.txt", cfg))


def graphs(c: Ctx) -> None:
    """Graph and RDF on for one folder; then the graphs removed (RDF kept on repositories), then all."""
    s = c.src
    job = c.ingest("folder graphs/ with graph + RDF", s.body("graphs", graph=True, rdf=True))
    c.configs["graphs"] = job.get("config_id")
    time.sleep(5)

    def indexed():   # (the ingest-status response, g1.txt's indexed map)
        st = c.backend.ingest_status(s.status_body(["graphs/g1.txt"], "graphs"))
        return st, ((st.get("items") or [{}])[0].get("indexed") or {})

    st, ix = indexed()
    c.check("ingest status shows the graph and RDF columns", st.get("show_graph") and st.get("show_rdf"),
            f"show_graph={st.get('show_graph')} show_rdf={st.get('show_rdf')}")
    c.check("g1.txt in vector, search, graph and RDF",
            all(ix.get(t) for t in ("vector", "search", "graph", "rdf")), json.dumps(ix))
    results = c.backend.search(f"{c.tag} Ada Lovelace Analytical Engine", top_k=10, source_auth=s.source_auth())
    c.check("hybrid search finds g1.txt's text", "Lovelace" in json.dumps(results), f"{len(results)} results")

    if not (s.row_actions or s.single_row):
        c.report.note("no removal for this source (Processing rows and /api/sync/remove: repositories and single-row sources)")
        return
    body = {"data_source": s.name, "item_actions": [s.row("graphs/g1.txt", "remove_graph", enabled_rdf=True)]}
    body.update(s.config("graphs"))
    c.ingest("row: remove the property graph, keep RDF", body)
    _, ix = indexed()
    c.check("after remove_graph: graph gone, RDF / vector / search kept",
            not ix.get("graph") and ix.get("rdf") and ix.get("vector") and ix.get("search"), json.dumps(ix))
    if s.row_actions:   # repositories: /api/sync/remove with its default targets (every store)
        c.backend.remove(s.status_body(["graphs/g1.txt"], "graphs"))
        what = "/api/sync/remove (default targets)"
    else:
        body = {"data_source": s.name, "item_actions": [s.row("graphs/g1.txt", "remove_all")]}
        body.update(s.config("graphs"))
        c.ingest("row: remove from every store", body)
        what = "row remove_all"
    st, ix = indexed()
    item = (st.get("items") or [{}])[0]
    c.check(f"after {what}: nothing left in any store",
            not any(ix.values()) if ix else item.get("status") in ("removed", "none"),
            f"status={item.get('status')} {json.dumps(ix)}")


def late(c: Ctx) -> None:
    """After periodic refreshes (interval set to 60 s): what was out of scope is still out."""
    s, cfg = c.src, c.configs.get("sel")
    for cid in filter(None, c.configs.values()):
        try:
            c.backend.set_interval(cid, 60)
        except Exception as e:
            c.report.note(f"interval of {cid[:8]} not set: {e}")
    time.sleep(c.late_wait)
    outside = [("out", "o.txt"), ("out", "new-out.txt")]
    if s.multiselect:
        outside += [("sel", "b.txt"), ("sel", "Other/e.txt"), ("sel", "new-root.txt")]
        if s.recursive_option:
            outside += [("sel", "Sub/Deep/d.txt"), ("sel", "Sub/Deep/new2.txt")]
    if s.row_actions:
        outside.append(("sel", "Sub/new3.txt"))
    for folder_, rel in outside:
        c.check(f"after a periodic refresh: {folder_}/{rel} still not followed", not c.followed(folder_, rel, cfg))


def drive(c: Ctx) -> None:
    """Google Drive: one existing file moved into sel/Sub/Deep, followed, edited, moved within, moved out."""
    s = c.src
    job = c.ingest("folder sel/ (the file two levels down)", s.body("sel"))
    cfg = c.configs["sel"] = job.get("config_id")

    def entry() -> Optional[Dict[str, Any]]:
        # Drive documents sit in the tree by name, not by folder path
        for d in c.tree.client.query_all("SELECT * FROM SysFile WHERE " + under(f"{c.tree.root}/{s.tree_type}")):
            if (d.get("sys_path") or "").endswith("/" + s.file_name):
                for st in d.get("fg_docstate_states") or []:
                    if st.get("configId") == cfg:
                        return st
        return None

    time.sleep(5)
    c.check("the nested file followed", entry() is not None)
    before = (entry() or {}).get("contentHash")
    s.edit(c.mark("D"))
    c.wait_check("edit followed", lambda: (entry() or {}).get("contentHash") not in (None, before))
    s.move_file("sel/Sub")
    time.sleep(90)
    c.check("moved within sel/: still followed", entry() is not None)
    s.move_file(None)
    c.wait_check("moved out of sel/: no longer followed", lambda: entry() is None)


ORDER: List[str] = ["select", "search", "follow", "delete", "move", "folder", "rule", "recursive", "graphs", "late"]
SCENARIOS: Dict[str, Callable[[Ctx], None]] = {
    "select": select, "search": search, "follow": follow, "delete": delete, "move": move, "folder": folder,
    "rule": rule, "recursive": recursive, "graphs": graphs, "late": late, "drive": drive,
}


def applies(name: str, s: Source, graph_sources: List[str]) -> bool:
    if not s.uploads:
        return name == "drive"
    if name == "drive":
        return False
    if name == "folder":
        return s.folder_rename and not s.recursive_option
    if name in ("rule",):
        return s.row_actions
    if name == "recursive":
        return s.recursive_option
    if name == "graphs":
        return s.name in graph_sources
    return True
