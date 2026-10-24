"""Per-object scope rules in the OpenArch tree (INCREMENTAL_STATE_STORE=openarch).

A rule is set on one source object -- a folder or a document -- and says what Flexible GraphRAG
does with it, one flag at a time:

- ``searchVector``: in the search + vector index (OpenArch, or VECTOR_DB / SEARCH_DB);
- ``pgGraph`` / ``rdfGraph``: in the property graph / the RDF graph;
- ``autoSync``: its source changes are followed.

A flag a rule does not set is inherited. A document's effective flags come, flag by flag, from
the nearest rule: its own, else its closest folder's (a folder rule covers its documents at any
depth when ``recursive``, else only those directly in it). Setting a flag on a folder clears that
flag on the rules below it, since the change applied to the whole folder; rules left with no
flag go. Folder inclusion and subfolder exclusion are folder rules with the flags on / off.

The Processing tab's per-row choices become rules (``row_flags``). Rules live on the objects'
mirrors in the source tree (``<OPENARCH_ROOT_PATH>/<source type>/<system id>/<path>``): the
document, or its folder, with the ``FgRule`` mixin (schema ``fgrule``, fields ``fg_rule_*``). Each
document with data source state also carries the flags in effect for it (``FgFlags``, fields
``fg_flags_*``), recomputed when a rule of its source system changes, for queries.

Rules are matched by the objects' source paths and node ids (as the Processing tab's rows are,
incremental_updates/removal.py), not by their place in the OpenArch tree.

A rule that sets ``autoSync`` also names the data source (connection) that follows the object
(``fg_rule_configIds``): the one already following the folder above it, else the one that set it.
An auto sync of a filesystem, Alfresco or Nuxeo source watches the top-most objects whose rules
turn auto sync on for it (``connection_roots``), so turning a row's Auto Sync on or off only
writes a rule; several connections to one source system each follow their own objects.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from incremental_updates.ingest_status import Item, _depth_below, fs_item, fs_key, normalize_repo_path
from incremental_updates.removal import StateRow, item_matches, root_matches

logger = logging.getLogger("flexible_graphrag.incremental_system")

# Sources whose auto syncs watch the objects the rules follow (connection_roots); the others
# watch what their data source is configured with (a bucket, a container, a drive folder).
ROOT_SOURCES = ("filesystem", "alfresco", "nuxeo")

RULE_MIXIN = "FgRule"     # a rule set on a folder or document
FLAGS_MIXIN = "FgFlags"   # the flags in effect on a document
FLAGS = ("searchVector", "pgGraph", "rdfGraph", "autoSync")
RULE = {f: "fg_rule_" + f for f in FLAGS}        # searchVector -> fg_rule_searchVector
EFFECTIVE = {f: "fg_flags_" + f for f in FLAGS}  # searchVector -> fg_flags_searchVector

# The Processing tab's per-row action (main.ItemAction.action) as flags
ACTION_FLAGS: Dict[str, Dict[str, bool]] = {
    "ingest": {"searchVector": True, "pgGraph": True, "rdfGraph": True},
    "ingest_no_graph": {"searchVector": True, "pgGraph": False, "rdfGraph": False},
    "remove_graph": {"pgGraph": False, "rdfGraph": False},
    "remove_all": {"searchVector": False, "pgGraph": False, "rdfGraph": False},
    "keep": {},
}

_B = {"type": "boolean"}
RULE_SCHEMA = {"prefix": "fg_rule", "fields": {
    "fg_rule_sourceType": {"type": "string"}, "fg_rule_sourceId": {"type": "string"},
    "fg_rule_path": {"type": "string"}, "fg_rule_nodeId": {"type": "string"},
    "fg_rule_isFolder": _B, "fg_rule_recursive": _B, "fg_rule_updatedAt": {"type": "date"},
    **{RULE[f]: _B for f in FLAGS},
    "fg_rule_sourcePath": {"type": "string"},                # the path as the source names it (an OS path)
    "fg_rule_configIds": {"type": "fgdocstate#stringList"},  # the data sources following it
}}
FLAGS_SCHEMA = {"prefix": "fg_flags", "fields": {EFFECTIVE[f]: _B for f in FLAGS}}


def row_flags(action: Optional[str], auto_sync: Optional[bool] = None, graphs=None) -> Dict[str, bool]:
    """The flags a Processing tab row sets: its action's, plus its Auto Sync column when set.
    ``graphs`` (graph_flags.GraphFlags): the graphs an "ingest" row builds (default both); on a
    "remove_graph" row, the graphs it keeps (those are left as they are)."""
    flags = dict(ACTION_FLAGS.get(action or "keep", {}))
    if graphs is not None and (action or "keep") == "ingest":
        flags.update(pgGraph=bool(graphs.graph), rdfGraph=bool(graphs.rdf))
    if graphs is not None and action == "remove_graph":
        for flag, kept in (("pgGraph", graphs.graph), ("rdfGraph", graphs.rdf)):
            if kept:
                flags.pop(flag, None)
    if auto_sync is not None:
        flags["autoSync"] = bool(auto_sync)
    return flags


def match_item(data_source: str, path: str, node_id: Optional[str], is_folder: bool) -> Item:
    """A row as the rules match it: a filesystem path normalized as document_state keeps it, a
    repository path in its canonical form."""
    if data_source in ("filesystem", "upload"):
        return fs_item(path, is_folder)
    return Item(normalize_repo_path(path), is_folder, node_id)


def file_identity(data_source: str, path: str, node_id: Optional[str]) -> Optional[str]:
    """The source identity of a file row, as the stores' stable doc ids name it
    (``<config_id>:<identity>``)."""
    if data_source in ("filesystem", "upload"):
        return fs_key(path)
    return f"{data_source}://{node_id}" if node_id else None


@dataclass
class ScopeRule:
    item: Item                    # path (canonical), node id, folder or document
    flags: Dict[str, bool]        # only the flags the rule sets
    recursive: bool = False       # a folder rule: documents at any depth, else only direct ones
    oa_id: Optional[str] = None   # the OpenArch object carrying it
    config_ids: List[str] = field(default_factory=list)  # the data sources following it (autoSync)
    source_path: Optional[str] = None  # its path as the source names it

    def copy(self) -> "ScopeRule":
        return ScopeRule(self.item, dict(self.flags), self.recursive, self.oa_id, list(self.config_ids),
                         self.source_path)

    def rank(self, row: StateRow, ancestor_ids: Optional[List[str]] = None) -> Optional[int]:
        """How near the rule is to a document (0 = its own), or None when it does not cover it.
        ``ancestor_ids`` (nearest first, e.g. an Alfresco event's primary hierarchy) match folder
        rules by node id, so a document is placed even when its path is not known."""
        if not self.item.is_folder:
            return 0 if item_matches(self.item, row, True) else None
        if ancestor_ids and self.item.id:
            if self.item.id not in ancestor_ids:
                return None
            depth = ancestor_ids.index(self.item.id) + 1
            return depth if depth == 1 or self.recursive else None
        depth = _depth_below(_row_path(row.source_path, self.item.path), self.item.path)
        if depth is None or depth == 0 or (depth > 1 and not self.recursive):
            return None
        return depth

    def covers_rule(self, other: "ScopeRule") -> bool:
        """Whether ``other`` is a rule below this folder rule (within its reach)."""
        if not self.item.is_folder or other is self:
            return False
        depth = _depth_below(other.item.path, self.item.path)
        if depth is None or depth == 0:
            return False
        return self.recursive or depth == 1


def _row_path(source_path: str, rule_path: str) -> str:
    """A document's path in the form of a rule's: canonical, and lowercase for a Windows path
    (filesystem rules hold paths as document_state keys them, fs_key)."""
    path = normalize_repo_path(source_path)
    return path.lower() if _DRIVE.match(rule_path) else path


_DRIVE = re.compile(r"^/[a-z]:(/|$)")


def effective_flags(rules: Iterable[ScopeRule], row: StateRow,
                    ancestor_ids: Optional[List[str]] = None) -> Dict[str, Optional[bool]]:
    """A document's flags, each from the nearest rule that sets it (None: no rule does)."""
    ranked = sorted(((r.rank(row, ancestor_ids), r) for r in rules), key=lambda x: (x[0] is None, x[0] or 0))
    out: Dict[str, Optional[bool]] = {f: None for f in FLAGS}
    for rank, rule in ranked:
        if rank is None:
            break
        for f in FLAGS:
            if out[f] is None and f in rule.flags:
                out[f] = rule.flags[f]
    return out


def graphs_skipped(flags: Dict[str, Optional[bool]]) -> Optional[bool]:
    """Whether a document leaves the graphs out (the pipeline's skip_graph covers both): True
    when no graph is on and at least one is off, False when one is on, None when no rule says."""
    graphs = (flags.get("pgGraph"), flags.get("rdfGraph"))
    if True in graphs:
        return False
    return True if False in graphs else None


def sync_decision(flags: Dict[str, Optional[bool]]) -> Dict[str, Any]:
    """What the sync does with a document it is about to ingest: ``follow`` (ingest it or not),
    ``graph`` / ``rdf`` (the property graph / RDF graph: True or False from a rule, None: the data
    source's setting), ``skip_graph`` (the older single flag) and the ``reason`` when it is not
    followed."""
    out = {"follow": False, "graph": None, "rdf": None, "skip_graph": None}
    if flags.get("autoSync") is False:
        return {**out, "reason": "auto sync is off for it (scope rule)"}
    if flags.get("searchVector") is False:
        if graphs_skipped(flags) is False:
            # graphs without search + vector: not in the pipeline yet
            return {**out, "reason": "graphs only, without search + vector, is not supported yet (scope rule)"}
        return {**out, "reason": "excluded: search + vector and graphs off (scope rule)"}
    return {"follow": True, "graph": flags.get("pgGraph"), "rdf": flags.get("rdfGraph"),
            "skip_graph": graphs_skipped(flags), "reason": None}


def item_flags(rules: Iterable[ScopeRule], item: Item) -> Dict[str, Optional[bool]]:
    """The flags of a selected row: a document's effective flags; a folder's own rule, then
    those of the folders above it."""
    if not item.is_folder:
        return effective_flags(rules, StateRow(doc_id="", config_id="", source_id=item.id,
                                               source_path=item.path, synced={}))
    out: Dict[str, Optional[bool]] = {f: None for f in FLAGS}
    candidates = []
    for rule in rules:
        if not rule.item.is_folder:
            continue
        depth = _depth_below(item.path, rule.item.path)
        if depth is None or (depth > 1 and not rule.recursive):
            continue
        candidates.append((depth, rule))
    for _, rule in sorted(candidates, key=lambda x: x[0]):
        for f in FLAGS:
            if out[f] is None and f in rule.flags:
                out[f] = rule.flags[f]
    return out


def apply_rule(rules: List[ScopeRule], new: ScopeRule) -> Tuple[List[ScopeRule], List[ScopeRule]]:
    """Add or merge ``new`` into ``rules``: its flags overwrite the same object's, and a folder's
    flags clear the same flags on the rules below it. Returns (rules, rules changed or emptied)."""
    changed: List[ScopeRule] = []
    same = next((r for r in rules if _same_object(r.item, new.item)), None)
    if same is None:
        same = ScopeRule(item=new.item, flags={}, recursive=new.recursive)
        rules = rules + [same]
    same.flags.update(new.flags)
    same.recursive = new.recursive if new.item.is_folder else False
    same.item = Item(new.item.path, new.item.is_folder, new.item.id or same.item.id)  # its current path
    same.source_path = new.source_path or same.source_path
    if "autoSync" in new.flags and new.config_ids:
        same.config_ids = list(new.config_ids)  # who follows it now
    changed.append(same)
    if new.item.is_folder and new.flags:
        for rule in rules:
            if same.covers_rule(rule) and any(f in rule.flags for f in new.flags):
                for f in new.flags:
                    rule.flags.pop(f, None)
                changed.append(rule)
    return rules, changed


def _same_object(a: Item, b: Item) -> bool:
    if a.is_folder != b.is_folder:
        return False
    if a.id and b.id:
        return a.id == b.id  # a renamed / moved object keeps its node id
    return a.path == b.path


def follower(rules: Iterable[ScopeRule], item: Item, default: Optional[str]) -> Optional[str]:
    """The data source that follows an object whose auto sync a row sets: the one following the
    nearest folder above it with auto sync on (a row inside a sync is resumed there), else the
    one that followed the object itself, else ``default`` (the run's own, or the sync its new
    rows join)."""
    best: Optional[Tuple[int, ScopeRule]] = None
    for rule in rules:
        if not (rule.item.is_folder and rule.flags.get("autoSync") is True and rule.config_ids):
            continue
        depth = _depth_below(item.path, rule.item.path)
        if depth is None or depth == 0 or (depth > 1 and not rule.recursive):
            continue
        if best is None or depth < best[0]:
            best = (depth, rule)
    if best is not None:
        return best[1].config_ids[0]
    same = next((r for r in rules if _same_object(r.item, item)), None)
    if same is not None and same.config_ids:
        return same.config_ids[0]
    return default


def connection_roots(rules: Iterable[ScopeRule], config_id: str) -> List[ScopeRule]:
    """What a data source watches: the top-most objects whose rules turn auto sync on for it
    (a rule inside one of them is covered by it), by path."""
    mine = [r for r in rules if r.flags.get("autoSync") is True and config_id in r.config_ids]
    return sorted((r for r in mine if not any(o.covers_rule(r) for o in mine)), key=lambda r: r.item.path)


def roots_params(source_type: str, connection_params: Dict[str, Any], roots: List[ScopeRule]) -> Dict[str, Any]:
    """A data source's connection_params watching ``roots`` (connection_roots), in the form its
    detector reads: a filesystem's ``paths``; a repository's ``nodeDetails`` (and ``nodeIds``), or
    its ``path`` when it is rooted at one folder chosen by path. Entries already there are kept
    as they are."""
    cp = dict(connection_params or {})
    if source_type == "filesystem":
        stored = {fs_item(p, True).path: p for p in cp.get("paths") or [] if p}
        cp["paths"] = [stored.get(r.item.path) or r.source_path or r.item.path for r in roots]
        return cp
    old = [nd for nd in cp.get("nodeDetails") or [] if isinstance(nd, dict)]
    if not old and len(roots) == 1 and roots[0].item.is_folder and not roots[0].item.id:
        cp["path"] = roots[0].source_path or roots[0].item.path
        return cp
    details = []
    for r in roots:
        nd = next((d for d in old if root_matches(r.item, d.get("path") or "", d.get("id"))), None)
        if nd is None:
            path = r.source_path or r.item.path
            nd = {"name": path.rstrip("/").rsplit("/", 1)[-1], "path": path,
                  "isFile": not r.item.is_folder, "isFolder": r.item.is_folder}
            if r.item.id:
                nd = {"id": r.item.id, **nd}
        details.append(nd)
    cp["nodeDetails"] = details
    if cp.get("nodeIds") is not None:
        cp["nodeIds"] = [d["id"] for d in details if d.get("id")]
    return cp


# ── OpenArch storage ─────────────────────────────────────────────────────────────────────────

def _rule_of(doc: Dict[str, Any]) -> ScopeRule:
    return ScopeRule(
        item=Item(doc.get("fg_rule_path") or "/", bool(doc.get("fg_rule_isFolder")), doc.get("fg_rule_nodeId")),
        flags={f: bool(doc[RULE[f]]) for f in FLAGS if doc.get(RULE[f]) is not None},
        recursive=bool(doc.get("fg_rule_recursive")),
        oa_id=doc.get("sys_id"),
        config_ids=list(doc.get("fg_rule_configIds") or []),
        source_path=doc.get("fg_rule_sourcePath"),
    )


_CACHE_SECONDS = 30.0


class ScopeStore:
    """The rules of each source system, kept on their objects in the OpenArch source tree."""

    def __init__(self, registry):
        self.registry = registry          # openarch.registry.OpenArchRegistry
        self.client = registry.client
        self._cache: Dict[str, Tuple[float, List[ScopeRule]]] = {}
        self._lock = threading.Lock()

    # ----- reads -----

    def rules(self, cin_source: str, fresh: bool = False) -> List[ScopeRule]:
        """The rules of a source system (``cin_sourceId`` form, e.g. ``alfresco:<repository id>``)."""
        from openarch.client import hxql_literal
        with self._lock:
            hit = self._cache.get(cin_source)
            if hit and not fresh and time.monotonic() - hit[0] < _CACHE_SECONDS:
                return [r.copy() for r in hit[1]]
        docs = self.client.query_all(
            f"SELECT * FROM SysContent WHERE fg_rule_sourceId = {hxql_literal(cin_source)} AND {self.registry.in_sources}")
        rules = [_rule_of(d) for d in docs if d.get("fg_rule_path")]
        with self._lock:
            self._cache[cin_source] = (time.monotonic(), rules)
        return [r.copy() for r in rules]

    def rules_for(self, source_type: str, url: Optional[str] = None) -> List[ScopeRule]:
        """The rules of a source: of its repository at ``url``, or of every source system of that
        type (a filesystem: this host's)."""
        from openarch import source_system as ss
        from openarch.client import hxql_literal
        if source_type in ("filesystem", "upload") or url:
            kwargs = {f"{source_type}_config": {"url": url}} if url else {}
            return self.rules(ss.cin_source_id(*ss.source_system_for(source_type, kwargs)))
        docs = self.client.query_all(
            f"SELECT * FROM SysContent WHERE fg_rule_sourceType = {hxql_literal(source_type)} AND {self.registry.in_sources}")
        return [_rule_of(d) for d in docs if d.get("fg_rule_path")]

    def flags_for(self, cin_source: str, row: StateRow) -> Dict[str, Optional[bool]]:
        return effective_flags(self.rules(cin_source), row)

    # ----- writes -----

    def set_rules(self, source_type: str, system: str,
                  rows: Iterable[Tuple[str, Optional[str], bool, bool, Dict[str, bool]]],
                  owner: Optional[str] = None) -> int:
        """Record rows' flags as rules: each row is ``(path, node id, is folder, recursive,
        flags)`` as the Processing tab sends it (``path`` as the UI shows it). Folders are applied
        before the documents in them, shallow ones first. A row setting auto sync names the data
        source following it (``follower``; ``owner``: the run's own, or the sync its new rows
        join). Then the documents' effective flags are recomputed. Returns how many rules
        changed."""
        from openarch import source_system as ss
        cin_source = ss.cin_source_id(source_type, system)
        rules = self.rules(cin_source, fresh=True)
        display: Dict[int, str] = {}
        changed: Dict[int, ScopeRule] = {}
        incoming = []
        for path, node_id, is_folder, recursive, flags in rows:
            if not flags:
                continue
            item = match_item(source_type, path, node_id, is_folder)
            incoming.append((item, path, recursive, flags))
        incoming.sort(key=lambda x: (not x[0].is_folder, x[0].path.count("/")))
        for item, path, recursive, flags in incoming:
            new = ScopeRule(item=item, flags=dict(flags), recursive=recursive, source_path=path)
            if "autoSync" in flags:
                who = follower(rules, item, owner)
                new.config_ids = [who] if who else []
            rules, touched = apply_rule(rules, new)
            display[id(touched[0])] = path
            for rule in touched:
                changed[id(rule)] = rule
        for rule in changed.values():
            self._store(source_type, system, cin_source, rule, display.get(id(rule)))
        with self._lock:
            self._cache.pop(cin_source, None)
        if changed:
            self.recompute(cin_source)
        logger.info("OpenArch scope: %d rule(s) set for %s", len(changed), cin_source)
        return len(changed)

    def _store(self, source_type: str, system: str, cin_source: str, rule: ScopeRule,
               display_path: Optional[str]) -> None:
        """Write a rule on its object (created as a mirror when missing); a rule with no flag
        left is cleared, and a document mirror holding nothing else is deleted."""
        props: Dict[str, Any] = {
            "fg_rule_sourceType": source_type, "fg_rule_sourceId": cin_source, "fg_rule_path": rule.item.path,
            "fg_rule_nodeId": rule.item.id, "fg_rule_isFolder": rule.item.is_folder,
            "fg_rule_recursive": bool(rule.recursive) if rule.item.is_folder else None,
            "fg_rule_updatedAt": datetime.now(timezone.utc).isoformat(),
            **{RULE[f]: rule.flags.get(f) for f in FLAGS},
            "fg_rule_configIds": list(rule.config_ids),
        }
        if rule.source_path:
            props["fg_rule_sourcePath"] = rule.source_path
        if not rule.flags:
            if rule.oa_id:
                self._clear(rule.oa_id)
            return
        doc = self.client.get(rule.oa_id) if rule.oa_id else None
        if doc is None:
            doc = self._mirror(source_type, system, cin_source, rule, display_path)
        self.registry.update_with_mixin(doc, RULE_MIXIN, props)
        rule.oa_id = doc["sys_id"]

    def _clear(self, oa_id: str) -> None:
        doc = self.client.get(oa_id)
        if doc is None:
            return
        props = {k: None for k in RULE_SCHEMA["fields"]}
        if doc.get("sys_primaryType") == "SysFile" and not doc.get("fg_docstate_docIds") \
                and not (doc.get("cin_ingestProperties") or {}).get("fg_docIds"):
            from openarch.writer import delete_with_chunks
            delete_with_chunks(self.client, oa_id)
            return
        self.registry.update_with_mixin(doc, RULE_MIXIN, props)

    def _mirror(self, source_type: str, system: str, cin_source: str, rule: ScopeRule,
                display_path: Optional[str]) -> Dict[str, Any]:
        """The object a rule goes on: a document's (found by its identity, or created where the
        OpenArch store will write it), a folder's mirror folder."""
        from openarch import source_system as ss
        from openarch.client import hxql_literal
        from openarch.writer import create_source_document
        path = display_path or rule.item.path
        if not rule.item.is_folder:
            identity = file_identity(source_type, path, rule.item.id)
            if identity:
                docs = self.client.query(
                    f"SELECT * FROM SysFile WHERE cin_id = {hxql_literal(identity)} "
                    f"AND cin_sourceId = {hxql_literal(cin_source)} AND {self.registry.in_sources}", limit=5)["documents"]
                if docs:
                    return docs[0]
            name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            segments = ss.document_path(source_type, identity or path,
                                        {"file_path": path, "human_file_path": path, "file_name": name})
            body = {"sys_primaryType": "SysFile", "sys_mixinTypes": ["CinRemote", RULE_MIXIN],
                    "sys_title": name or segments[-1], "cin_id": identity or path, "cin_sourceId": cin_source,
                    "cin_paths": [path]}
            return create_source_document(self.client, self.registry.root_path, source_type, system,
                                          segments, body)
        folder = f"{self.registry.root_path}/{ss.source_folder(source_type, system)}"
        if rule.item.path != "/":
            segments = ss.document_path(source_type, path, {"file_path": path, "human_file_path": path})
            folder += "/" + "/".join(segments)
        self.client.ensure_folders(folder)
        return self.client.get_by_path(folder)

    # ----- what auto syncs watch -----

    def connection_roots(self, cin_source: str, config_id: str) -> Optional[List[ScopeRule]]:
        """The objects a data source watches (``connection_roots``); None when no rule names it."""
        rules = self.rules(cin_source, fresh=True)
        if not any(config_id in r.config_ids for r in rules):
            return None
        return connection_roots(rules, config_id)

    def claim_roots(self, cin_source: str, config_id: str, roots: List[Item]) -> bool:
        """Name a data source on the rules of the objects it watches (one registered before rules
        named their followers), when each has a rule with auto sync on that names no one else.
        Returns whether it did."""
        rules = self.rules(cin_source, fresh=True)
        found = []
        for item in roots:
            rule = next((r for r in rules if _same_object(r.item, item)), None)
            if rule is None or rule.flags.get("autoSync") is not True or \
                    (rule.config_ids and rule.config_ids != [config_id]):
                return False
            found.append(rule)
        for rule in found:
            if rule.config_ids != [config_id]:
                doc = self.client.get(rule.oa_id) if rule.oa_id else None
                if doc is not None:
                    self.registry.update_with_mixin(doc, RULE_MIXIN, {"fg_rule_configIds": [config_id]})
        with self._lock:
            self._cache.pop(cin_source, None)
        return bool(found)

    # ----- effective flags on the documents -----

    def recompute(self, cin_source: str) -> int:
        """Store each document's effective flags (the source system's documents with data source
        state). Returns how many changed."""
        from openarch.client import hxql_literal
        rules = self.rules(cin_source, fresh=True)
        n = 0
        for doc in self.client.query_all(
                f"SELECT * FROM SysFile WHERE cin_sourceId = {hxql_literal(cin_source)} AND fg_docstate_docIds IS NOT NULL "
                f"AND {self.registry.in_sources}"):
            props = self.effective_props(rules, doc)
            if any(doc.get(k) != v for k, v in props.items()):
                self.registry.update_with_mixin(doc, FLAGS_MIXIN, props)
                n += 1
        return n

    @staticmethod
    def effective_props(rules: List[ScopeRule], doc: Dict[str, Any]) -> Dict[str, Optional[bool]]:
        """A document's ``fg_rule_eff*`` values from its data source state's path and source id."""
        entries = doc.get("fg_docstate_states") or []
        entry = entries[0] if entries else {}
        row = StateRow(doc_id="", config_id="", source_id=entry.get("sourceId"),
                       source_path=entry.get("sourcePath") or "", synced={})
        flags = effective_flags(rules, row)
        return {EFFECTIVE[f]: flags[f] for f in FLAGS}
