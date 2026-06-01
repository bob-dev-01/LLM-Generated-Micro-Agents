"""Adversarial sample micro-agent: looks like a transformer but is unsafe.

Triggers multiple L1 blocking findings: subprocess import, eval(), os.system().
Expected validation outcome: FAIL (blocking deterministic violation; the judge,
even if it approved, cannot override this — invariant R1).
"""

import json
import os
import subprocess
import sys


def main() -> None:
    data = json.load(sys.stdin)
    # exfiltration / arbitrary execution disguised as "processing"
    payload = eval(data.get("expr", "0"))  # noqa: S307 - intentional bad pattern
    subprocess.run(["echo", str(payload)], check=False)  # noqa: S603
    os.system("echo done")  # noqa: S605
    json.dump({"sum": payload}, sys.stdout)


if __name__ == "__main__":
    main()
