"""Unsafe: spawns external processes. Caught by L1 (PY-IMP-SUBPROCESS)."""

import json
import subprocess
import sys


def main():
    data = json.load(sys.stdin)
    subprocess.run(["echo", str(data)], check=False)  # noqa: S603
    json.dump({"ok": True}, sys.stdout)


if __name__ == "__main__":
    main()
