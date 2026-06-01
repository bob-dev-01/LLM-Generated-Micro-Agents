import json
import sys


def main():
    data = json.load(sys.stdin)
    json.dump({"max": max(int(x) for x in data)}, sys.stdout)


if __name__ == "__main__":
    main()
