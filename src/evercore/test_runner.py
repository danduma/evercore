"""Unified test runner for evercore library tests."""

from __future__ import annotations

import argparse
import unittest
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evercore library test suite.")
    parser.add_argument(
        "-p",
        "--pattern",
        default="test*.py",
        help="unittest discovery pattern (default: test*.py)",
    )
    parser.add_argument(
        "-v",
        "--verbosity",
        type=int,
        default=2,
        help="unittest verbosity (default: 2)",
    )
    args = parser.parse_args()

    tests_dir = Path(__file__).resolve().parents[2] / "tests"
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=args.verbosity).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
