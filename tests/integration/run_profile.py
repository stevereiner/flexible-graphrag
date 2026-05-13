"""
Run the integration test suite against a single backend profile.

This script:
  1. Resolves the requested profile from env_profiles.py
  2. Writes a temporary .env file (overrides layered on base .env)
  3. Starts the flexible-graphrag backend as a subprocess
  4. Waits for it to become healthy
  5. Runs pytest (integration marker, **excluding** ``incremental`` — filesystem watch tests)
  6. Shuts the backend down
  7. Exits with pytest's return code

Usage:
    uv run tests/integration/run_profile.py --profile neo4j-llamaindex
    uv run tests/integration/run_profile.py --profile fuseki-rdf --test-args="-k fast"
    uv run tests/integration/run_profile.py --list
"""
from __future__ import annotations

import argparse
import datetime
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = REPO_ROOT / "flexible-graphrag"
BASE_ENV = BACKEND_DIR / ".env"
API_PORT = int(os.getenv("API_TEST_PORT", "8000"))
API_URL = f"http://localhost:{API_PORT}"

# Add parent so we can import the modules
sys.path.insert(0, str(REPO_ROOT))

from tests.integration.api_client import APIClient
from tests.integration.env_profiles import PROFILES, build_env_file, list_profiles


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run integration tests for one backend profile")
    p.add_argument("--profile", "-p", help="Profile name to run against")
    p.add_argument("--list", action="store_true", help="List all available profiles and exit")
    p.add_argument("--base-env", default=str(BASE_ENV), help="Base .env to layer overrides on top of")
    p.add_argument("--no-start", action="store_true",
                   help="Don't start the backend — assume it's already running")
    p.add_argument("--test-path", default="tests/integration/",
                   help="Pytest test path (default: tests/integration/)")
    p.add_argument(
        "--test-args",
        default="",
        help=(
            "Extra pytest CLI args (shlex-split; omit for default -m integration and not incremental). "
            "Examples: -m integration  |  -k fast  |  use marker kwarg in code for complex -m (see run_pytest)."
        ),
    )
    p.add_argument("--timeout", type=int, default=120,
                   help="Seconds to wait for backend to become healthy (default: 120; "
                        "lifespan loads HybridSearchSystem + DB connections before /api/health answers)")
    return p.parse_args()


LOGS_DIR = REPO_ROOT / "tests" / "integration" / "logs"


def _backend_log_path(label: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    # Sanitize: replace chars illegal in Windows filenames, collapse runs
    import re
    safe = re.sub(r'[|:/\\<>?"*]', "-", label)
    safe = re.sub(r'\s+', "_", safe)
    safe = re.sub(r'[-_]{2,}', "-", safe).strip("-_")
    return LOGS_DIR / f"backend-{safe}-{ts}.log"


def start_backend(env_file: Path, log_path: Path | None = None) -> subprocess.Popen:
    """Start the backend subprocess, writing all output to *log_path* (not the terminal)."""
    env = os.environ.copy()
    for k, v in dotenv_values(env_file).items():
        if v is not None:
            env[k] = v
    env["ENV_FILE"] = str(env_file)
    env.setdefault("PYTHONUNBUFFERED", "1")

    if log_path is None:
        stdout = stderr = None          # inherit terminal (fallback / --no-start mode)
    else:
        log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
        stdout = stderr = log_fh        # redirect all backend noise to file
        print(f"[run_profile] Backend log: {log_path}")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(API_PORT)],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=stdout,
        stderr=stderr,
    )
    # Attach the file handle so stop_backend can close it
    proc._log_fh = log_fh if log_path else None  # type: ignore[attr-defined]
    return proc


def stop_backend(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    fh = getattr(proc, "_log_fh", None)
    if fh:
        fh.close()


def _extract_k_value(extra_args: str) -> str:
    """If extra_args is purely a ``-k EXPR`` pair, return EXPR (preserving spaces).

    Returns empty string if extra_args contains other flags so the caller can
    fall back to shlex splitting.
    """
    s = extra_args.strip()
    if s.startswith("-k ") and s.count(" -") <= 0:
        # Simple "-k EXPR" with no other flags — return everything after "-k "
        return s[3:].strip()
    return ""


def _split_pytest_extra_args(extra_args: str) -> list[str]:
    """Split pytest CLI args; quoted ``-m "expr"`` must survive (``split()`` breaks that)."""
    s = extra_args.strip()
    if not s:
        return []
    return shlex.split(s, posix=os.name != "nt")


# Passed as two argv entries so pytest never sees quote characters in the -m expression.
DEFAULT_MARKER = "integration and not incremental"


def run_pytest(
    test_path: str,
    extra_args: str = "",
    *,
    marker: str | None = None,
    label: str | None = None,
    extra_env: dict[str, str] | None = None,
    pytest_k: str = "",
    exitfirst: bool = False,
) -> int:
    """Run pytest, streaming only test-module log lines to the console.

    Backend logs go to the backend log file.  Only ``logger.info()`` calls
    from the test files (``tests.integration.*``) appear in the terminal,
    keeping output clean: test results + search answers, nothing else.

    Pass *label* (e.g. ``"neo4j·qdrant·llamaindex"``) to display it in the
    pytest session header so the combo is visible next to each result line.
    Pass *extra_env* to inject additional env vars into the pytest subprocess
    (e.g. INTEGRATION_WATCH_DIR for incremental tests).
    Pass *pytest_k* as the -k expression (spaces preserved correctly).
    Pass *exitfirst=True* to add -x (stop on first failure).
    """
    env = os.environ.copy()
    if label:
        env["MATRIX_LABEL"] = label
    if extra_env:
        env.update(extra_env)

    cmd = [sys.executable, "-m", "pytest", test_path]
    if marker is not None:
        cmd.extend(["-m", marker])
        # Also honour extra_args (e.g. -k filter from --inc-ops) alongside the marker.
        # Extract -k value and pass as two separate args so spaces in the expression
        # (e.g. "test_add or test_delete") are never split into extra path arguments.
        if extra_args.strip():
            _k_val = _extract_k_value(extra_args)
            if _k_val:
                cmd.extend(["-k", _k_val])
            else:
                cmd.extend(_split_pytest_extra_args(extra_args))
    elif not extra_args.strip():
        cmd.extend(["-m", DEFAULT_MARKER])
    else:
        _k_val = _extract_k_value(extra_args)
        if _k_val:
            cmd.extend(["-k", _k_val])
        else:
            cmd.extend(_split_pytest_extra_args(extra_args))

    # Structured args passed directly (bypass the string-splitting path entirely)
    if pytest_k:
        cmd.extend(["-k", pytest_k])
    if exitfirst:
        cmd.append("-x")
    cmd.extend([
        f"--base-url={API_URL}",
        "-v",
        # Stream test-module log calls live (search answers etc.) — no backend noise
        # since the backend runs in a separate process writing to its own log file.
        "--log-cli-level=INFO",
        "--log-cli-format=%(message)s",
    ])
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    return result.returncode


def main() -> int:
    args = parse_args()

    if args.list:
        print("Available profiles:")
        for name in list_profiles():
            overrides = PROFILES[name]
            desc = ", ".join(f"{k}={v}" for k, v in list(overrides.items())[:4])
            print(f"  {name:<35} {desc}")
        return 0

    if not args.profile:
        print("Error: --profile is required. Use --list to see options.", file=sys.stderr)
        return 1

    if args.profile not in PROFILES:
        print(f"Unknown profile: {args.profile}. Use --list to see options.", file=sys.stderr)
        return 1

    # Build the env file
    env_file = build_env_file(args.profile, base_env=args.base_env)
    print(f"[run_profile] Profile: {args.profile}")
    print(f"[run_profile] Env file: {env_file}")

    proc = None
    log_path: Path | None = None
    try:
        if not args.no_start:
            log_path = _backend_log_path(args.profile)
            print(f"[run_profile] Starting backend on port {API_PORT} ...")
            proc = start_backend(env_file, log_path=log_path)
            client = APIClient(base_url=API_URL)
            if not client.wait_until_healthy(max_wait=args.timeout):
                print(
                    f"[run_profile] ERROR: Backend did not become healthy within {args.timeout}s",
                    file=sys.stderr,
                )
                if proc.poll() is not None:
                    print(
                        f"[run_profile] Process exited early with code {proc.returncode}.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "[run_profile] Process still running: startup may be slow. "
                        "Retry with a larger --timeout, or confirm Neo4j/port "
                        f"{API_PORT} are available for this profile.",
                        file=sys.stderr,
                    )
                if log_path:
                    print(f"[run_profile] Backend log: {log_path}", file=sys.stderr)
                return 2
            print("[run_profile] Backend is healthy.")
        else:
            print(f"[run_profile] --no-start: expecting backend already at {API_URL}")

        rc = run_pytest(args.test_path, args.test_args)
        return rc

    finally:
        if proc:
            print("[run_profile] Stopping backend ...")
            stop_backend(proc)
        env_file.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
