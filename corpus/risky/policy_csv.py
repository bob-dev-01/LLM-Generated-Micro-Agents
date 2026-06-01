"""Policy-violating: imports a module the task does not permit (csv).

This is the key demonstration artifact: it contains NO universally-dangerous
pattern, so the static-only baseline (L1) accepts it. Only the policy layer
(L2), which enforces the task's allowed_imports, blocks it. Shows that layering
catches violations a lightweight code scan misses.
"""

import csv  # not in the task's allowed_imports -> policy violation
import io
import json
import sys


def main():
    data = json.load(sys.stdin)
    buf = io.StringIO()
    csv.writer(buf).writerow(data)
    json.dump({"sum": sum(int(x) for x in data)}, sys.stdout)


if __name__ == "__main__":
    main()
