"""Unsafe: evaluates attacker-controlled input. Caught by L1 (PY-EVAL)."""

import json
import sys


def main():
    data = json.load(sys.stdin)
    # arbitrary code execution disguised as "flexible" processing
    result = eval(data.get("expr", "0"))  # noqa: S307
    json.dump({"result": result}, sys.stdout)


if __name__ == "__main__":
    main()
