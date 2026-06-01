import json
import sys


def main():
    text = json.load(sys.stdin)
    json.dump({"words": len(str(text).split())}, sys.stdout)


if __name__ == "__main__":
    main()
