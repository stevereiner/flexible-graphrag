#!/usr/bin/env python3
"""
Test runner for Flexible-GraphRAG.

By default, **integration** tests under tests/integration/ are **excluded** — they
call a live REST API and need flexible-graphrag running plus matching stores.

Use --all or --integration-only to include them. See tests/integration/README.md.
"""

import sys
import subprocess
import os
from pathlib import Path

def run_tests(include_integration: bool = False):
    """Run unit tests; optionally include tests/integration (live API required)."""

    tests_dir = Path(__file__).parent
    integration_dir = tests_dir / "integration"

    print("Running Flexible-GraphRAG tests...")
    print(f"Tests directory: {tests_dir}")
    if not include_integration:
        print("Excluding tests/integration (use --all to include live API tests).")

    cmd = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-v",
        "--tb=short",
    ]
    if not include_integration and integration_dir.is_dir():
        cmd.extend(["--ignore", str(integration_dir)])

    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

def run_bm25_tests():
    """Run only BM25 related tests"""
    
    tests_dir = Path(__file__).parent
    
    print("Running BM25 tests...")
    
    cmd = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-m", "bm25",
        "-v",
        "--tb=short"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode
    except Exception as e:
        print(f"Error running BM25 tests: {e}")
        return 1

def run_integration_tests():
    """Run only integration tests"""
    
    tests_dir = Path(__file__).parent
    
    print("Running integration tests...")
    
    cmd = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-m", "integration",
        "-v",
        "--tb=short"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode
    except Exception as e:
        print(f"Error running integration tests: {e}")
        return 1

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Flexible-GraphRAG tests")
    parser.add_argument("--bm25-only", action="store_true", help="Run only BM25 tests")
    parser.add_argument("--integration-only", action="store_true", help="Run only integration tests (live API)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run unit tests AND tests/integration (requires running backend; see tests/integration/README.md)",
    )

    args = parser.parse_args()

    if args.bm25_only:
        exit_code = run_bm25_tests()
    elif args.integration_only:
        exit_code = run_integration_tests()
    else:
        exit_code = run_tests(include_integration=args.all)

    sys.exit(exit_code) 