"""Auto-sync matrix: multiselect, recursive, add / edit / delete / move / rename, Processing rows
with Auto Sync off, periodic refreshes and (for a few sources) graphs, per data source, checked
in the OpenArch state store's tree.

    venv-3.14/Scripts/python.exe tests/integration/autosync/run_autosync.py
    ... --sources alfresco,nuxeo --scenarios select,follow,move
    ... --backend http://127.0.0.1:8000          (a backend you started yourself)

By default it starts its own backend (port 8010) from this checkout with .env plus:
ENABLE_INCREMENTAL_UPDATES=true, INCREMENTAL_STATE_STORE=openarch and its own OpenArch roots
(/fg-e2e-sources, /fg-e2e-datasources), so it never touches the trees of a backend you run on
/fg-sources. Vector, search and graph stores are the .env ones: run scripts/cleanup.py after.
See README.md.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import REPO, Backend, Report, Tree, env  # noqa: E402
from scenarios import ORDER, SCENARIOS, Ctx, applies  # noqa: E402
from sources import SOURCES  # noqa: E402

ALL = ["filesystem", "alfresco", "nuxeo", "s3", "azure_blob", "box", "sharepoint", "onedrive", "google_drive"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sources", default=",".join(ALL), help=f"comma-separated; default all: {','.join(ALL)}")
    p.add_argument("--scenarios", default="", help=f"comma-separated subset of {','.join(ORDER)} (default: all that apply)")
    p.add_argument("--graph-sources", default="filesystem,alfresco,s3",
                   help="sources that also run the graphs scenario (graph + RDF on); default filesystem,alfresco,s3")
    p.add_argument("--backend", default="", help="use this running backend instead of starting one")
    p.add_argument("--port", type=int, default=8010, help="port of the backend this starts (default 8010)")
    p.add_argument("--openarch-url", default=env("OPENARCH_URL") or "http://localhost:8088")
    p.add_argument("--root", default="/fg-e2e-sources", help="OPENARCH_ROOT_PATH of the backend under test")
    p.add_argument("--datasources-root", default="/fg-e2e-datasources", help="its OPENARCH_DATASOURCES_PATH")
    p.add_argument("--openarch-store", action="store_true",
                   help="ENABLE_OPENARCH=true: OpenArch is also the vector and search store")
    p.add_argument("--no-reset", action="store_true",
                   help="keep the e2e roots in OpenArch (by default a backend this starts begins with them "
                        "deleted, so earlier runs' syncs don't come back with it)")
    p.add_argument("--keep", action="store_true",
                   help="leave the test folders in the sources and, with a backend this starts, its OpenArch trees")
    p.add_argument("--late-wait", type=int, default=100, help="seconds the late scenario waits (interval 60 s)")
    return p.parse_args()


def main() -> int:
    a = parse_args()
    run = datetime.now().strftime("%m%d%H%M")
    results_dir = REPO / "tests" / "integration" / "results"
    tree = Tree(a.openarch_url, a.root)
    backend = None
    if a.backend:
        backend = Backend(a.backend)
        if not backend.healthy():
            print(f"no backend answers at {a.backend}")
            return 2
    else:
        if not a.no_reset:
            for path in (a.root, a.datasources_root):
                print(f"reset: {path} {'deleted' if tree.delete_folder(path) else 'not there'}")
        overrides = {
            "ENABLE_INCREMENTAL_UPDATES": "true",
            "INCREMENTAL_STATE_STORE": "openarch",
            "OPENARCH_URL": a.openarch_url,
            "OPENARCH_ROOT_PATH": a.root,
            "OPENARCH_DATASOURCES_PATH": a.datasources_root,
            "POSTGRES_INCREMENTAL_URL": "",
            "ENABLE_OPENARCH": "true" if a.openarch_store else "false",
        }
        if a.openarch_store:
            # OpenArch indexes 1024-dimension vectors only (OpenAI text-embedding-3-*: asked for that size)
            overrides["OPENAI_EMBEDDING_DIMENSION"] = env("OPENARCH_TEST_EMBEDDING_DIMENSION") or "1024"
        log = results_dir / f"autosync-{run}-backend.log"
        print(f"starting the backend on port {a.port} (log {log}) ...", flush=True)
        backend = Backend.start(a.port, overrides, log)
    print(f"backend {backend.url} | OpenArch {a.openarch_url} {a.root} | run {run}", flush=True)

    report = Report()
    chosen = [s.strip() for s in a.scenarios.split(",") if s.strip()] or ORDER + ["drive"]
    graph_sources = [s.strip() for s in a.graph_sources.split(",") if s.strip()]
    skipped = {}
    t_start = time.time()
    try:
        for i, name in enumerate(s.strip() for s in a.sources.split(",") if s.strip()):
            print(f"\n=== {name}", flush=True)
            report.source, report.scenario = name, "setup"
            try:
                src = SOURCES[name](run)
            except Exception as e:   # missing settings or client library
                skipped[name] = f"{type(e).__name__}: {e}"[:200]
                print(f"  SKIP  {skipped[name]}")
                continue
            ctx = Ctx(src, backend, tree, report, tag=f"kga{run}x{i}", late_wait=a.late_wait)
            try:
                src.setup(ctx.tag)
                for scenario in ORDER + ["drive"]:
                    if scenario not in chosen or not applies(scenario, src, graph_sources):
                        continue
                    report.scenario = scenario
                    print(f"  -- {scenario}", flush=True)
                    try:
                        SCENARIOS[scenario](ctx)
                    except Exception as e:
                        report.error(f"{type(e).__name__}: {e}")
                        traceback.print_exc(limit=3)
            except Exception as e:
                report.error(f"setup: {type(e).__name__}: {e}")
                traceback.print_exc(limit=3)
            finally:
                if not a.keep:
                    try:
                        src.cleanup()
                    except Exception as e:
                        print(f"  cleanup of {name} failed: {e}")
    finally:
        if not a.backend:
            backend.stop()
            # its OpenArch trees go with it, unless --keep (scripts/cleanup.py --openarch removes them too)
            if not a.keep:
                for path in (a.root, a.datasources_root):
                    try:
                        tree.delete_folder(path)
                    except Exception as e:
                        print(f"  could not delete {path}: {e}")

    print("\n=== summary")
    for name, s in report.summary().items():
        print(f"  {name:13} {s['passed']:3} passed  {s['failed']:3} failed")
    for name, why in skipped.items():
        print(f"  {name:13} skipped: {why}")
    for r in report.failed():
        print(f"  FAIL  {r['source']} / {r['scenario']}: {r['check']}  {r['detail']}")
    out = results_dir / f"autosync-{run}.json"
    report.save(out, {"run": run, "backend": backend.url, "openarch_root": a.root, "openarch_store": a.openarch_store,
                      "minutes": round((time.time() - t_start) / 60, 1), "skipped": skipped})
    print(f"report: {out}")
    return 1 if report.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
