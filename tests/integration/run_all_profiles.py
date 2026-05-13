"""
Run all integration test profiles sequentially and report a summary.

For CI: iterates every profile in env_profiles.py, starts the backend,
runs tests, stops the backend, and accumulates pass/fail counts.

You can limit which profiles to run:
    uv run tests/integration/run_all_profiles.py --include "neo4j*" "fuseki*"
    uv run tests/integration/run_all_profiles.py --exclude "*spanner*" "*gremlin*"
    uv run tests/integration/run_all_profiles.py --only-fast    # skips @pytest.mark.slow
    uv run tests/integration/run_all_profiles.py --clean        # run cleanup.py before each profile
    uv run tests/integration/run_all_profiles.py --chunker llamaindex

Backend logs for each profile are written to tests/integration/logs/backend-<profile>-<ts>.log.
Results are written to tests/integration/results/run_<timestamp>.json.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.integration.env_profiles import list_profiles
from tests.integration.run_profile import (
    _backend_log_path,
    build_env_file,
    start_backend,
    stop_backend,
    run_pytest,
    APIClient,
    API_URL,
    BACKEND_DIR,
)

RESULTS_DIR = Path(__file__).parent / "results"
CLEANUP_SCRIPT = REPO_ROOT / "scripts" / "cleanup.py"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run all integration profiles")
    p.add_argument("--include", nargs="*", metavar="GLOB",
                   help="Only run profiles matching these globs")
    p.add_argument("--exclude", nargs="*", metavar="GLOB",
                   help="Skip profiles matching these globs")
    p.add_argument("--only-fast", action="store_true",
                   help="Skip @pytest.mark.slow tests")
    p.add_argument(
        "--clean", action="store_true",
        help="Run scripts/cleanup.py --matrix-clean before each profile to wipe leftover "
             "vector/search/graph/RDF data (skips Postgres state tables and log files). "
             "Ensures each profile starts from a blank slate. "
             "Cleanup errors are logged as warnings and do not abort the run.",
    )
    p.add_argument(
        "--chunker", choices=["llamaindex", "langchain"],
        help="Filter to profiles that use the specified CHUNKER_BACKEND "
             "(langchain = lc-pipe profiles; llamaindex = default profiles). "
             "Profiles without an explicit CHUNKER_BACKEND key are treated as 'llamaindex'.",
    )
    p.add_argument(
        "--test-file", metavar="PATH",
        help="Run only this pytest file/path instead of the full tests/integration/ directory. "
             "Example: --test-file tests/integration/test_lc_pipeline.py",
    )
    p.add_argument("--base-env", default=str(REPO_ROOT / "flexible-graphrag" / ".env"))
    p.add_argument("--timeout", type=int, default=60)
    return p.parse_args()


def matches_any(name: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in globs)


def _profile_chunker_backend(profile_name: str) -> str:
    """Return the effective CHUNKER_BACKEND for a profile ('llamaindex' or 'langchain')."""
    from tests.integration.env_profiles import PROFILES
    profile_overrides = PROFILES.get(profile_name, {})
    return profile_overrides.get("CHUNKER_BACKEND", "llamaindex").lower()


def select_profiles(args: argparse.Namespace) -> list[str]:
    all_profiles = list_profiles()
    selected = all_profiles
    if args.include:
        selected = [p for p in selected if matches_any(p, args.include)]
    if args.exclude:
        selected = [p for p in selected if not matches_any(p, args.exclude)]
    if getattr(args, "chunker", None):
        selected = [p for p in selected
                    if _profile_chunker_backend(p) == args.chunker.lower()]
    return selected


def _run_cleanup(env_file: Path, profile: str) -> None:
    """
    Run scripts/cleanup.py --matrix-clean using the profile's env file so the
    right DB endpoints are targeted.  Errors are printed but never abort the run.
    """
    if not CLEANUP_SCRIPT.exists():
        print(f"  [WARN] --clean: {CLEANUP_SCRIPT} not found, skipping cleanup.")
        return

    from dotenv import dotenv_values
    env = os.environ.copy()
    for k, v in dotenv_values(env_file).items():
        if v is not None:
            env[k] = v
    env["ENV_FILE"] = str(env_file)

    print(f"  [clean] Running cleanup for profile '{profile}' ...")
    try:
        result = subprocess.run(
            [sys.executable, str(CLEANUP_SCRIPT), "--matrix-clean"],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  [WARN] Cleanup exited {result.returncode} for '{profile}':")
            for line in (result.stdout + result.stderr).splitlines()[-10:]:
                print(f"         {line}")
        else:
            lines = (result.stdout + result.stderr).strip().splitlines()
            summary_line = lines[-1] if lines else "(no output)"
            print(f"  [clean] Done: {summary_line}")
    except subprocess.TimeoutExpired:
        print(f"  [WARN] Cleanup timed out after 120s for profile '{profile}' — continuing.")
    except Exception as exc:
        print(f"  [WARN] Cleanup error for '{profile}': {exc} — continuing.")


def main() -> int:
    args = parse_args()
    profiles = select_profiles(args)
    if not profiles:
        print("No profiles selected.", file=sys.stderr)
        return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_file = RESULTS_DIR / f"run_{timestamp}.json"

    summary: list[dict] = []
    overall_rc = 0

    print(f"Running {len(profiles)} profiles: {profiles}")
    if args.clean:
        print("  --clean enabled: cleanup.py will run before each profile.\n")
    else:
        print("  Tip: pass --clean to wipe DB data before each profile for independent runs.\n")

    for idx, profile in enumerate(profiles, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(profiles)}] Profile: {profile}")
        print('='*60)

        env_file = build_env_file(profile, base_env=args.base_env)
        log_path = _backend_log_path(profile)
        proc = None
        start_time = time.time()
        try:
            if args.clean:
                _run_cleanup(env_file, profile)

            print(f"  Backend log -> {log_path}")
            proc = start_backend(env_file, log_path=log_path)
            client = APIClient(base_url=API_URL)
            healthy = client.wait_until_healthy(max_wait=args.timeout)
            if not healthy:
                print(f"  SKIP (backend not healthy within {args.timeout}s — see {log_path})")
                summary.append({
                    "profile": profile,
                    "status": "skipped",
                    "reason": "unhealthy",
                    "log": str(log_path),
                })
                continue

            if args.only_fast:
                rc = run_pytest(
                    args.test_file or "tests/integration/",
                    marker="integration and not incremental and not slow",
                )
            else:
                rc = run_pytest(args.test_file or "tests/integration/", "")

            elapsed = round(time.time() - start_time, 1)
            status = "passed" if rc == 0 else "failed"
            print(f"\n  [{status.upper()}] {profile} in {elapsed}s")
            if rc != 0:
                print(f"  Backend log: {log_path}")
            summary.append({
                "profile": profile,
                "status": status,
                "exit_code": rc,
                "elapsed_s": elapsed,
                "log": str(log_path),
            })
            if rc != 0:
                overall_rc = rc

        except Exception as exc:
            summary.append({
                "profile": profile,
                "status": "error",
                "error": str(exc),
                "log": str(log_path),
            })
            overall_rc = 1
        finally:
            if proc:
                stop_backend(proc)
            env_file.unlink(missing_ok=True)

    # Write JSON summary
    results_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"Results written to: {results_file}")

    # Print table
    passed  = sum(1 for r in summary if r["status"] == "passed")
    failed  = sum(1 for r in summary if r["status"] == "failed")
    skipped = sum(1 for r in summary if r["status"] in ("skipped", "error"))
    print(f"\nSummary: {passed} passed / {failed} failed / {skipped} skipped")
    for r in summary:
        icon = {"passed": "[OK]", "failed": "[FAIL]", "skipped": "[SKIP]", "error": "[ERR]"}.get(
            r["status"], "?"
        )
        log_hint = f"  log: {Path(r['log']).name}" if r.get("log") and r["status"] != "passed" else ""
        print(f"  {icon}  {r['profile']}{log_hint}")

    return overall_rc


if __name__ == "__main__":
    sys.exit(main())
