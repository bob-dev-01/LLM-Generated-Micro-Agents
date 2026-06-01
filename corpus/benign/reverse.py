import json
import sys


def main():
    text = json.load(sys.stdin)
    json.dump({"reversed": str(text)[::-1]}, sys.stdout)


if __name__ == "__main__":
    main()
