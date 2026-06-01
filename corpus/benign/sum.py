import json
import sys


def main():
    data = json.load(sys.stdin)
    json.dump({"sum": sum(int(x) for x in data)}, sys.stdout)


if __name__ == "__main__":
    main()
