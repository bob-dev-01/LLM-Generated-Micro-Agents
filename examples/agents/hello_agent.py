"""Benign sample micro-agent: sums a JSON list of integers from stdin.

Uses only allowed imports (json, sys); no network, subprocess, eval, or fs writes.
Expected validation outcome: PASS.
"""

import json
import sys


def main() -> None:
    data = json.load(sys.stdin)
    result = {"sum": sum(int(x) for x in data)}
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
